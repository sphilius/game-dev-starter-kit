"""gate3d.py - measures whether a 3D model (.glb) is fit to ship in a Godot web game.

    python gate3d.py hero.glb --kind character --height 1.8 --clips idle,walk,attack --loops idle,walk
    python gate3d.py crate.glb --kind prop --max-tris 500 --report crate_gate.json

Three layers, cheapest first (each later layer is skipped if its tool is not available):

  FILE (plain Python, milliseconds; see glb_facts.py)
    tri_budget     triangles <= --max-tris (default: character 15000, prop 3000, environment 60000)
    height         size on the Y axis within 10 % of --height (skipped when --height is not given)
    y_up           the model stands on +Y: for characters, Y must be the longest axis
    origin         the feet are on the ground (lowest point within 2 cm of y = 0) and the model
                   is centred over its origin (within 10 % of its width), so it does not float,
                   sink, or orbit when rotated
    bones          bone count <= --max-bones (64: a safe ceiling for mobile web)
    influences     at most 4 bone weights per vertex (Godot's Compatibility renderer limit)
    clip_names     every clip in --clips exists; each is 0.1 to 10 s long

  BLENDER (blender -b, about 12 s; see blender_gate.py). Needs --blender or BLENDER.
    non_manifold   non-manifold edges <= --max-non-manifold (0 for characters and props;
                   not enforced for environment pieces, where open edges are normal)
    bend           worst joint keeps >= 0.5 of its thickness at a 90 degree bend (rigged only)
    turnaround     four preview renders were written (front, side, back, three-quarter)

  GODOT (headless import + pipeline3d's asset_audit.gd, about 15 s). Needs --godot or GODOT.
    godot_import   imports with no errors (warnings are listed in the detail)
    clip_loops     every clip in --loops is set to loop after import; no other clip loops
    web_size       what the asset adds to the build (imported scene + textures) <= --budget-kb

Exit code 0 = every gate that ran passed, 1 = at least one failed.
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import glb_facts  # noqa: E402

GATES_DIR = pathlib.Path(__file__).resolve().parent
GODOT_TEMPLATE = GATES_DIR.parents[2] / "pipeline3d" / "godot_template"
DEFAULT_MAX_TRIS = {"character": 15000, "prop": 3000, "environment": 60000}
# The headless (dummy) renderer logs these while making thumbnails; they are not asset problems.
HARMLESS = ("texture_2d_get", "Condition \"!t\" is true", "RenderingServerDefault")


def check(name: str, passed: bool | None, value, limit, detail: str = "") -> dict:
    """One gate result. passed=None means the gate was skipped (it does not count as a failure)."""
    return {"name": name, "passed": passed, "value": value, "limit": limit, "detail": detail}


def find_tool(explicit: str | None, env_name: str) -> str | None:
    """The path given on the command line, else the environment variable, if it really exists."""
    candidate = explicit or os.environ.get(env_name)
    if candidate == "off" or not candidate:
        return None
    return candidate if (shutil.which(candidate) or pathlib.Path(candidate).is_file()) else None


# --- Layer 1: the file itself -------------------------------------------------------------

def file_gates(facts: dict, kind: str, height: float | None, max_tris: int, max_bones: int,
               clips: list[str]) -> list[dict]:
    """The gates that only need the numbers glb_facts read out of the file."""
    out = [check("tri_budget", facts["triangles"] <= max_tris, facts["triangles"], max_tris,
                 f"{facts['meshes']} mesh(es), {facts['materials']} material(s)")]
    size = facts["size"]
    if size is None:
        return out + [check("height", False, None, height, "the file has no mesh bounds")]
    if height is None:
        out.append(check("height", None, size[1], None, "no --height given"))
    else:
        off = abs(size[1] - height) / height
        out.append(check("height", off <= 0.10, size[1], f"{height} +-10 %", f"size x,y,z = {size} m"))
    if kind == "character":
        out.append(check("y_up", size[1] >= max(size[0], size[2]) * 0.9, size, "Y is the longest axis",
                         "a character lying on its side was exported Z-up"))
    else:
        out.append(check("y_up", None, size, None, "only checked for characters"))
    lowest = facts["bounds_min"][1]
    centre_x = (facts["bounds_min"][0] + facts["bounds_max"][0]) / 2.0
    centre_z = (facts["bounds_min"][2] + facts["bounds_max"][2]) / 2.0
    drift = max(abs(centre_x) / max(size[0], 1e-6), abs(centre_z) / max(size[2], 1e-6))
    grounded = abs(lowest) <= max(0.02, 0.02 * size[1])
    if kind == "environment":
        out.append(check("origin", None, {"lowest_y": lowest}, None, "not enforced for environment pieces"))
    else:
        out.append(check("origin", grounded and drift <= 0.10,
                         {"lowest_y": round(lowest, 3), "centre_offset": round(drift, 3)},
                         {"lowest_y": "0 +-2 cm", "centre_offset": 0.10},
                         "origin should sit on the ground, under the middle of the model"))
    rigged = facts["bones"] > 0
    out.append(check("bones", facts["bones"] <= max_bones if rigged else None, facts["bones"], max_bones,
                     "" if rigged else "not rigged"))
    out.append(check("influences", facts["max_influences"] <= 4 if rigged else None, facts["max_influences"], 4,
                     "bone weights per vertex" if rigged else "not rigged"))
    have = {clip["name"]: clip["seconds"] for clip in facts["clips"]}
    if clips:
        missing = [name for name in clips if name not in have]
        bad_length = [f"{name} {have[name]} s" for name in clips if name in have and not 0.1 <= have[name] <= 10.0]
        out.append(check("clip_names", not missing and not bad_length, sorted(have), clips,
                         f"missing {missing}" if missing else (f"odd lengths: {bad_length}" if bad_length else
                                                               ", ".join(f"{n} {have[n]} s" for n in clips))))
    else:
        out.append(check("clip_names", None, sorted(have), None, "no --clips given"))
    return out


# --- Layer 2: Blender ---------------------------------------------------------------------

def blender_gates(glb: pathlib.Path, blender: str | None, kind: str, max_non_manifold: int | None,
                  min_retention: float, render_dir: pathlib.Path | None, rigged: bool) -> list[dict]:
    """Runs blender_gate.py in a background Blender and turns its JSON into gate results."""
    names = ["non_manifold", "bend", "turnaround"]
    if blender is None:
        return [check(name, None, None, None, "skipped: pass --blender or set BLENDER") for name in names]
    with tempfile.TemporaryDirectory() as folder:
        result_path = pathlib.Path(folder) / "result.json"
        command = [blender, "-b", "--factory-startup", "--python-exit-code", "1",
                   "-P", str(GATES_DIR / "blender_gate.py"), "--",
                   f"glb={glb}", f"out={result_path}", f"bend={'1' if rigged else '0'}"]
        if render_dir:
            command.append(f"render_dir={render_dir}")
        try:
            run = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            return [check(name, False, "timeout", None, "Blender did not finish in 600 s") for name in names]
        if run.returncode != 0 or not result_path.is_file():
            tail = (run.stdout + run.stderr).strip().splitlines()[-3:]
            return [check(name, False, "crash", None, " | ".join(tail)) for name in names]
        result = json.loads(result_path.read_text(encoding="utf-8"))
    topo = result["topology"]
    enforce = max_non_manifold is not None and kind != "environment"
    out = [check("non_manifold", topo["non_manifold_edges"] <= max_non_manifold if enforce else None,
                 topo["non_manifold_edges"], max_non_manifold if enforce else None,
                 f"{topo['loose_vertices']} loose vertices" + ("" if enforce else "; reported only for environment pieces"))]
    bend = result.get("bend", {"tested": False, "reason": "not rigged"})
    if bend.get("tested"):
        out.append(check("bend", bend["worst_retention"] >= min_retention, bend["worst_retention"], min_retention,
                         f"worst joint {bend['worst_joint']} of {bend['joints_tested']} tested"))
    else:
        out.append(check("bend", None, None, min_retention, bend.get("reason", "")))
    renders = [p for p in result.get("renders", []) if pathlib.Path(p).is_file() and pathlib.Path(p).stat().st_size > 2000]
    if render_dir:
        out.append(check("turnaround", len(renders) >= 4, len(renders), 4, str(render_dir)))
    else:
        out.append(check("turnaround", None, 0, 4, "no --render-dir given"))
    return out


# --- Layer 3: Godot -----------------------------------------------------------------------

def godot_gates(glb: pathlib.Path, godot: str | None, loops: list[str], budget_kb: float) -> list[dict]:
    """Imports the model in a throwaway copy of pipeline3d's Godot template and audits it there."""
    names = ["godot_import", "clip_loops", "web_size"]
    if godot is None:
        return [check(name, None, None, None, "skipped: pass --godot or set GODOT") for name in names]
    with tempfile.TemporaryDirectory() as folder:
        project = pathlib.Path(folder) / "project"
        shutil.copytree(GODOT_TEMPLATE, project, ignore=shutil.ignore_patterns(".godot"))
        assets = project / "assets"
        for old in assets.glob("*"):                   # audit only this one model
            if old.suffix.lower() in (".glb", ".gltf", ".fbx"):
                old.unlink()
        shutil.copy(glb, assets / glb.name)
        audit_path = pathlib.Path(folder) / "audit.json"
        try:
            imported = subprocess.run([godot, "--headless", "--path", str(project), "--import"],
                                      capture_output=True, text=True, timeout=300)
            subprocess.run([godot, "--headless", "--path", str(project), "-s", "res://tools/asset_audit.gd",
                            "--", "res://assets", f"--out={audit_path}"], capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return [check(name, False, "timeout", None, "Godot did not finish in 300 s") for name in names]
        log = (imported.stdout + imported.stderr).splitlines()
        errors = [line.strip() for line in log if "ERROR" in line and not any(h in line for h in HARMLESS)]
        if not audit_path.is_file():
            return [check(name, False, "no audit", None, "; ".join(errors[:3]) or "asset_audit.gd wrote nothing")
                    for name in names]
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        entry = next((a for a in audit["assets"] if a["path"].endswith(glb.name)), None)
        # Everything Godot generated for this model: the scene plus any textures it extracted.
        cache = project / ".godot" / "imported"
        payload = sum(f.stat().st_size for f in cache.glob(f"{glb.stem}*") if f.suffix != ".md5") if cache.is_dir() else 0
    if entry is None:
        return [check(name, False, "not audited", None, "the model did not appear in the audit") for name in names]
    problems = errors + entry["errors"]
    out = [check("godot_import", not problems, len(problems), 0,
                 "; ".join(problems[:3]) if problems else ("warnings: " + "; ".join(entry["warnings"][:3]) if entry["warnings"] else "clean import"))]
    looping = sorted(clip["name"] for clip in entry["clips"] if clip.get("loop"))
    if entry["clips"]:
        out.append(check("clip_loops", looping == sorted(loops), looping, sorted(loops),
                         "clips that loop after import vs. the ones that should"))
    else:
        out.append(check("clip_loops", None, [], sorted(loops), "no clips"))
    kb = round(payload / 1024.0, 1)
    out.append(check("web_size", kb <= budget_kb, kb, budget_kb, "imported scene + textures (what the asset adds to the .pck)"))
    return out


# The entry point other scripts import: run_gate(path, kind=..., height=...) -> report dict.
def run_gate(glb: pathlib.Path, *, kind: str = "prop", height: float | None = None, max_tris: int | None = None,
             max_bones: int = 64, clips: tuple[str, ...] = (), loops: tuple[str, ...] = (),
             max_non_manifold: int | None = 0, min_retention: float = 0.5, budget_kb: float = 2048.0,
             render_dir: pathlib.Path | None = None, blender: str | None = None, godot: str | None = None) -> dict:
    """Runs all three layers and returns the report dictionary (same shape as gate2d's)."""
    started = time.perf_counter()
    glb = pathlib.Path(glb).resolve()
    facts = glb_facts.facts(glb)
    limit = max_tris if max_tris is not None else DEFAULT_MAX_TRIS[kind]
    checks = file_gates(facts, kind, height, limit, max_bones, list(clips))
    checks += blender_gates(glb, find_tool(blender, "BLENDER"), kind, max_non_manifold, min_retention,
                            pathlib.Path(render_dir).resolve() if render_dir else None, facts["bones"] > 0)
    checks += godot_gates(glb, find_tool(godot, "GODOT"), list(loops), budget_kb)
    failed = [c["name"] for c in checks if c["passed"] is False]
    return {
        "asset": glb.name, "kind": kind, "passed": not failed, "failed": failed,
        "skipped": [c["name"] for c in checks if c["passed"] is None],
        "facts": facts, "checks": checks, "gate_seconds": round(time.perf_counter() - started, 2),
    }


def build_parser() -> argparse.ArgumentParser:
    """Command-line options (argparse writes --help from these)."""
    parser = argparse.ArgumentParser(description="Gate a 3D model: measure it against shipping limits.")
    parser.add_argument("glb", type=pathlib.Path)
    parser.add_argument("--kind", default="prop", choices=["character", "prop", "environment"])
    parser.add_argument("--height", type=float, default=None, help="expected height in metres")
    parser.add_argument("--max-tris", type=int, default=None)
    parser.add_argument("--max-bones", type=int, default=64)
    parser.add_argument("--clips", default="", help="required animation names, comma separated")
    parser.add_argument("--loops", default="", help="which of them must loop, comma separated")
    parser.add_argument("--max-non-manifold", type=int, default=0)
    parser.add_argument("--min-retention", type=float, default=0.5)
    parser.add_argument("--budget-kb", type=float, default=2048.0)
    parser.add_argument("--render-dir", type=pathlib.Path, default=None, help="write turnaround PNGs here")
    parser.add_argument("--blender", default=None, help="Blender exe (or set BLENDER); 'off' skips that layer")
    parser.add_argument("--godot", default=None, help="Godot console exe (or set GODOT); 'off' skips that layer")
    parser.add_argument("--report", type=pathlib.Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> dict:
    """Parses options, runs the gates, prints a one-line verdict per gate, writes the report."""
    args = build_parser().parse_args(argv)
    split = lambda text: tuple(part.strip() for part in text.split(",") if part.strip())   # "a, b" -> ("a", "b")
    report = run_gate(args.glb, kind=args.kind, height=args.height, max_tris=args.max_tris,
                      max_bones=args.max_bones, clips=split(args.clips), loops=split(args.loops),
                      max_non_manifold=args.max_non_manifold, min_retention=args.min_retention,
                      budget_kb=args.budget_kb, render_dir=args.render_dir, blender=args.blender, godot=args.godot)
    for c in report["checks"]:
        verdict = "skip" if c["passed"] is None else ("PASS" if c["passed"] else "FAIL")
        print(f"  {verdict}  {c['name']:<13} {c['value']}  (limit {c['limit']})  {c['detail']}")
    print(f"{'PASSED' if report['passed'] else 'FAILED: ' + ', '.join(report['failed'])}"
          f"  {report['asset']}  ({report['gate_seconds']} s)")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    sys.exit(0 if main()["passed"] else 1)

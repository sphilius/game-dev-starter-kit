# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
forge.py - run one asset through the whole pipeline from a JSON manifest.

    python forge.py manifests/wolf.json            # run / resume
    python forge.py manifests/wolf.json --from rig # redo from a stage
    python forge.py manifests/wolf.json --only export
    python forge.py manifests/wolf.json --status   # show what's done / waiting

Stages (each is skipped when its output already exists, so re-running resumes):
    concept   reference image      Nano Banana (banana.py) or a manual gate
    generate  raw mesh             gen3d.py (tripo | meshy | rodin), a procedural Blender script, or a file
    cleanup   game-ready mesh      cleanup_for_godot.py
    rig       skeleton + skin      quadruped_rig.py | Mixamo/AccuRIG (manual gate) | tripo/meshy API
    animate   named clips          procedural | clips folder (Mixamo, ActorCore, mocap) | tripo/meshy API
    export    final GLB            export_for_godot.py (+ collision, copy into the Godot project)
    godot     import + audit       godot --headless --import, tools/asset_audit.gd

Exit codes: 0 done, 3 waiting for a manual step (instructions printed), 1 error.
Environment: BLENDER, GODOT (paths to the executables; default: on PATH),
             TRIPO_API_KEY / MESHY_API_KEY / RODIN_API_KEY for cloud generation.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BLENDER_DIR = os.path.join(HERE, "blender")
BANANA = os.path.join(os.path.dirname(HERE), ".agents", "skills", "nano-banana", "scripts", "banana.py")
STAGES = ["concept", "generate", "cleanup", "rig", "animate", "export", "godot"]
API_RIGS = ("tripo", "meshy")


class ManualStep(Exception):
    """Raised when a human has to do something in a web app; the message says what."""


# ----------------------------------------------------------------------------- helpers

def _exe(env, default):
    path = os.environ.get(env) or shutil.which(default)
    if not path:
        raise RuntimeError(f"{default} not found: set {env}=/path/to/{default}")
    return path


def _blender(script, config, workdir, label):
    cfg_path = os.path.join(workdir, ".forge", f"{label}.json")
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w") as fh:
        json.dump(config, fh, indent=1)
    cmd = [_exe("BLENDER", "blender"), "-b", "--factory-startup", "-P", os.path.join(BLENDER_DIR, script),
           "--", "--config", cfg_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    with open(os.path.join(workdir, ".forge", f"{label}.log"), "w") as fh:
        fh.write(proc.stdout + proc.stderr)
    match = re.findall(r"^PIPELINE_RESULT (.*)$", proc.stdout, re.M)
    result = json.loads(match[-1]) if match else {"ok": False}
    if proc.returncode != 0 or not result.get("ok"):
        raise RuntimeError(f"{script} failed (see .forge/{label}.log): {result.get('error') or proc.stderr[-400:]}")
    return result


def _gen3d(args):
    sys.path.insert(0, HERE)
    import gen3d  # noqa: E402  (same folder)
    from io import StringIO
    buf, old = StringIO(), sys.stdout
    sys.stdout = buf
    try:
        code = gen3d.main(args)
    finally:
        sys.stdout = old
    out = json.loads(buf.getvalue() or "{}")
    if code != 0 or not out.get("ok"):
        raise RuntimeError(f"gen3d {' '.join(args[:3])} failed: {out.get('error')}")
    return out


def _glb_to_fbx(src, dst):
    expr = ("import bpy\n"
            "for o in list(bpy.data.objects): bpy.data.objects.remove(o)\n"
            f"bpy.ops.import_scene.gltf(filepath={src!r})\n"
            f"bpy.ops.export_scene.fbx(filepath={dst!r}, path_mode='COPY', embed_textures=True, "
            "apply_scale_options='FBX_SCALE_ALL', add_leaf_bones=False)\n")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run([_exe("BLENDER", "blender"), "-b", "--factory-startup", "--python-expr", expr],
                   check=True, capture_output=True)


# ----------------------------------------------------------------------------- forge

class Forge:
    def __init__(self, manifest_path):
        with open(manifest_path) as fh:
            self.m = json.load(fh)
        self.name = self.m["name"]
        base = os.path.dirname(os.path.abspath(manifest_path))
        self.workdir = os.path.abspath(os.path.expanduser(self.m.get("workdir") or os.path.join(base, "..", "build", self.name)))
        self.base = base
        for d in ("refs", "incoming", "incoming/clips", "work", "handoff", "export"):
            os.makedirs(os.path.join(self.workdir, d), exist_ok=True)
        self.state_path = os.path.join(self.workdir, "forge_state.json")
        self.state = json.load(open(self.state_path)) if os.path.exists(self.state_path) else {}

    def p(self, *parts):
        return os.path.join(self.workdir, *parts)

    def src(self, path):
        """Manifest paths are relative to the manifest file."""
        return path if os.path.isabs(os.path.expanduser(path)) else os.path.join(self.base, path)

    def save(self):
        with open(self.state_path, "w") as fh:
            json.dump(self.state, fh, indent=1)

    def out(self, stage):
        return (self.state.get(stage) or {}).get("output")

    def latest_mesh(self, before):
        for st in reversed(STAGES[:STAGES.index(before)]):
            if self.out(st) and str(self.out(st)).endswith((".glb", ".fbx", ".gltf")):
                return self.out(st)
        return None

    # --- stages -------------------------------------------------------------

    def concept(self):
        c = self.m.get("concept")
        if not c:
            return None, "skipped (no concept section)"
        out = self.p("refs", os.path.basename(c.get("out", f"{self.name}_front.png")))
        if c.get("image") and os.path.exists(self.src(c["image"])):
            shutil.copy2(self.src(c["image"]), out)
            return out, "copied existing reference"
        if os.path.exists(out):
            # Generated (or hand-placed) on an earlier run and left there = approved.
            # Delete it to generate a new one.
            return out, "using existing reference"
        if c.get("tool") == "banana" and shutil.which("uv") and os.path.exists(BANANA):
            cmd = ["uv", "run", BANANA, "-p", c["prompt"], "-f", out, "-m", c.get("model", "nano-banana-2")]
            for ref in c.get("style_refs", []):
                cmd += ["-i", self.src(ref)]
            subprocess.run(cmd, check=True)
            raise ManualStep(f"Reference generated at {out}. Check it against the pass list in the "
                             f"runbook (full body, arms apart, open hands, flat light). Regenerate or edit if "
                             f"needed, then re-run forge.")
        raise ManualStep(f"Generate a reference image with this prompt (Nano Banana / Gemini, Flux, "
                         f"Midjourney, Bing Image Creator) and save it as {out}, or set concept.image:\n\n"
                         f"{c.get('prompt', '(no prompt in manifest)')}")

    def generate(self):
        g = self.m["generate"]
        raw = self.p("incoming", f"{self.name}_raw.glb")
        if g.get("procedural"):
            cfg = dict(g.get("config", {}))
            cfg["export_path"] = raw
            cfg.setdefault("clear_scene", True)
            rep = _blender(g["procedural"], cfg, self.workdir, "generate")
            return raw, rep
        if g.get("file"):
            shutil.copy2(self.src(g["file"]), raw)
            return raw, {"copied": g["file"]}
        provider = g["provider"]
        args = ["run", "--provider", provider, "--mode", g.get("mode", "image"), "--out", raw]
        image = g.get("image") or self.out("concept")
        if g.get("mode", "image") in ("image", "multiview"):
            for img in ([image] if isinstance(image, str) else image):
                args += ["--image", self.src(img)]
        if g.get("prompt"):
            args += ["--prompt", g["prompt"]]
        for k, v in g.get("options", {}).items():
            args += ["--opt", f"{k}={json.dumps(v)}"]
        rep = _gen3d(args)
        return raw, rep

    def cleanup(self):
        rig = (self.m.get("rig") or {}).get("method", "none")
        c = self.m.get("cleanup", {})
        if c is False or rig in API_RIGS:
            return self.out("generate"), "skipped (API rig uses the provider's mesh as-is)" if rig in API_RIGS else "skipped"
        out = self.p("work", f"{self.name}_clean.glb")
        cfg = {"import_path": self.out("generate"), "export_path": out, "object_name": self.name, **c}
        return out, _blender("cleanup_for_godot.py", cfg, self.workdir, "cleanup")

    def rig(self):
        r = self.m.get("rig") or {"method": "none"}
        method = r["method"]
        src = self.out("cleanup") or self.out("generate")
        if method == "none":
            return src, "no rig"
        if method == "quadruped":
            out = self.p("work", f"{self.name}_rigged.glb")
            anim = (self.m.get("animations") or {}).get("method", "procedural")
            cfg = {"import_path": src, "clear_scene": True, "export_path": out,
                   "clip_prefix": r.get("clip_prefix", ""), **r.get("config", {})}
            if anim != "procedural":
                cfg["clips"] = []
            return out, _blender("quadruped_rig.py", cfg, self.workdir, "rig")
        if method in ("mixamo", "accurig", "manual"):
            rigged = self.p("incoming", f"{self.name}_rigged.fbx")
            if os.path.exists(rigged):
                return rigged, f"using {rigged}"
            upload = self.p("handoff", f"{self.name}_for_rigging.fbx")
            _glb_to_fbx(src, upload)
            steps = {
                "mixamo": ("1. mixamo.com -> Upload Character -> " + upload,
                           "2. Place markers: chin, wrists, elbows, knees, groin. Skeleton LOD: Standard (65).",
                           "3. Download: FBX Binary, With Skin, T-pose, no animation."),
                "accurig": ("1. Open AccuRIG (free, Reallusion) -> Load " + upload,
                            "2. Rig Body (+ fingers) -> check poses -> Export -> FBX, Mixamo-compatible bone names.",
                            "3. Save the export."),
            }.get(method, ("1. Rig " + upload + " in your tool of choice.", "2. Export FBX with skin.", "3. Save it."))
            raise ManualStep("\n".join(steps) + f"\n4. Save the rigged file as {rigged} and re-run forge.")
        if method in API_RIGS:
            gen_task = json.load(open(self.out("generate") + ".gen3d.json"))["task"]
            out = self.p("incoming", f"{self.name}_rigged.glb")
            args = ["rig", "--provider", method, "--task", gen_task, "--out", out]
            for k, v in r.get("options", {}).items():
                args += ["--opt", f"{k}={json.dumps(v)}"]
            return out, _gen3d(args)
        raise ValueError(f"unknown rig method {method}")

    def animate(self):
        a = self.m.get("animations") or {"method": "none"}
        method = a["method"]
        rigged = self.out("rig")
        if method in ("none", "procedural"):
            return rigged, f"{method}: clips come from the rig stage" if method == "procedural" else "no clips"
        clips_dir = self.p("incoming", "clips")
        if method in API_RIGS:
            rig_task = json.load(open(rigged + ".gen3d.json"))["task"]
            for clip_name, anim in a.get("clips", {}).items():
                dest = os.path.join(clips_dir, f"{clip_name}.glb")
                if not os.path.exists(dest):
                    _gen3d(["animate", "--provider", method, "--task", rig_task, "--animation", str(anim), "--out", dest])
        have = [f for f in os.listdir(clips_dir) if f.lower().endswith((".fbx", ".glb", ".gltf"))]
        wanted = a.get("expect", [])
        missing = [w for w in wanted if not any(re.sub(r"[^a-z0-9]", "", w.lower()) in re.sub(r"[^a-z0-9]", "", f.lower()) for f in have)]
        if method == "clips_dir" and (not have or missing):
            raise ManualStep(
                f"Put one animation file per clip in {clips_dir} (file name = clip name).\n"
                f"Missing: {missing or 'all'}\n"
                "Mixamo: open each animation on your uploaded character, tick 'In Place' for locomotion,\n"
                "        Download -> FBX Binary, 30 fps, Skin: WITHOUT Skin.\n"
                "ActorCore / Rokoko Vision / DeepMotion: export FBX on the same skeleton.\n"
                "Then re-run forge.")
        out = self.p("work", f"{self.name}_animated.glb")
        cfg = {"character_path": rigged, "clips_dir": clips_dir, "export_path": out,
               "rename": a.get("rename", {}), "strip_root_motion": a.get("strip_root_motion", []),
               "hips_bone": a.get("hips_bone", "mixamorig:Hips")}
        return out, _blender("merge_clips.py", cfg, self.workdir, "animate")

    def export(self):
        e = self.m.get("export", {})
        src = self.latest_mesh("export")
        out = self.p("export", f"{self.name}.glb")
        proj = e.get("godot_project")
        cfg = {"import_path": src, "export_path": out, "collision": e.get("collision"),
               "copy_to": os.path.join(os.path.expanduser(self.src(proj)), e.get("assets_dir", "assets")) if proj else None}
        return out, _blender("export_for_godot.py", cfg, self.workdir, "export")

    def godot(self):
        proj = (self.m.get("export") or {}).get("godot_project")
        if not proj:
            return None, "skipped (no export.godot_project)"
        proj = os.path.expanduser(self.src(proj))
        godot = _exe("GODOT", "godot")
        imp = subprocess.run([godot, "--headless", "--path", proj, "--import"], capture_output=True, text=True)
        if imp.returncode != 0:
            raise RuntimeError(f"godot --import failed ({imp.returncode}): {(imp.stderr or imp.stdout)[-600:]}")
        lines = [l for l in imp.stdout.splitlines() if l.startswith("[pipeline_import]") and self.name in l]
        audit_path = self.p("work", "godot_audit.json")
        if os.path.exists(audit_path):
            os.remove(audit_path)          # never judge this run by a stale audit
        aud = subprocess.run([godot, "--headless", "--path", proj, "-s", "res://tools/asset_audit.gd", "--",
                              "res://assets", f"--out={audit_path}"], capture_output=True, text=True)
        if not os.path.exists(audit_path):
            raise RuntimeError(f"Godot audit produced no report ({aud.returncode}): {(aud.stderr or aud.stdout)[-600:]}")
        audit = json.load(open(audit_path))
        exported = os.path.basename(self.out("export") or f"{self.name}.glb")
        mine = [x for x in audit.get("assets", []) if os.path.basename(x["path"]) == exported]
        if not mine:
            raise RuntimeError(f"{exported} is missing from the Godot audit of res://assets")
        if any(x["errors"] for x in mine):
            raise RuntimeError(f"Godot audit errors: {[x['errors'] for x in mine]}")
        return audit_path, {"import": lines, "audit": mine}

    # --- driver -------------------------------------------------------------

    def run(self, start=None, only=None):
        forced = [only] if only else (STAGES[STAGES.index(start):] if start else [])
        for s in forced:
            self.state.pop(s, None)
        for stage in ([only] if only else STAGES):
            done = self.state.get(stage, {})
            if done.get("status") == "done" and (not done.get("output") or os.path.exists(done["output"])):
                print(f"[forge] {stage:9s} done     {done.get('output') or ''}")
                continue
            print(f"[forge] {stage:9s} running...", flush=True)
            try:
                output, report = getattr(self, stage)()
            except ManualStep as step:
                self.state[stage] = {"status": "waiting", "instructions": str(step)}
                self.save()
                print(f"[forge] {stage:9s} WAITING FOR YOU\n\n{step}\n")
                return 3
            except Exception as exc:  # noqa: BLE001 - report any stage failure the same way
                self.state[stage] = {"status": "error", "error": str(exc)}
                self.save()
                print(f"[forge] {stage:9s} ERROR: {exc}")
                return 1
            self.state[stage] = {"status": "done", "output": output, "report": report}
            self.save()
            print(f"[forge] {stage:9s} done     {output or ''}")
        print(f"[forge] {self.name}: complete -> {self.out('export')}")
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--from", dest="start", choices=STAGES)
    ap.add_argument("--only", choices=STAGES)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    f = Forge(a.manifest)
    if a.status:
        for s in STAGES:
            st = f.state.get(s, {})
            print(f"{s:9s} {st.get('status', '-'):8s} {st.get('output') or st.get('error') or ''}")
        return 0
    return f.run(a.start, a.only)


if __name__ == "__main__":
    sys.exit(main())

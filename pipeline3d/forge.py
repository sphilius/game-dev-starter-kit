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
    generate  raw mesh             gen3d.py (tripo | meshy | rodin), a procedural Blender script, or a file;
                                   with generate.fit_reference the procedural creature is fitted to the
                                   concept image first (fit_reference.py, Gemini vision)
    cleanup   game-ready mesh      cleanup_for_godot.py
    rig       skeleton + skin      quadruped_rig.py (+ bend_test.py: joints keep thickness at 90 deg)
                                   | Mixamo/AccuRIG (manual gate) | tripo/meshy API
    animate   named clips          procedural | clips folder (Mixamo, ActorCore, mocap) | tripo/meshy API
    export    final GLB            export_for_godot.py (+ collision, copy into the Godot project)
    godot     import + audit       godot --headless --import, tools/asset_audit.gd

Exit codes: 0 done, 3 waiting for a manual step (instructions printed), 1 error.
Environment: BLENDER, GODOT (paths to the executables; default: on PATH),
             TRIPO_API_KEY / MESHY_API_KEY / RODIN_API_KEY for cloud generation,
             GEMINI_API_KEY for Nano Banana references and reference fitting.
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
GODOT_TEMPLATE = os.path.join(HERE, "godot_template")
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


def ensure_godot_project(proj):
    """Make sure `proj` is a Godot project before forge copies assets into it or imports.

    Missing, empty, or holding only what forge itself put there (assets/, .godot/): create it
    from godot_template/, never overwriting a file that is already there. A template copied one
    level too deep (Copy-Item / cp -r into an existing folder) or any other folder without a
    project.godot: stop with the fix, rather than fill an unrelated folder with the template."""
    if os.path.exists(os.path.join(proj, "project.godot")):
        return None
    nested = os.path.join(proj, os.path.basename(GODOT_TEMPLATE))
    if os.path.exists(os.path.join(nested, "project.godot")):
        raise RuntimeError(
            f"{proj} has no project.godot, but {nested} does: the template was copied one level too deep "
            f"(copying into a folder that already existed). Move it up and re-run forge:\n"
            f'  PowerShell: Copy-Item -Recurse -Force "{nested}\\*" "{proj}\\"; Remove-Item -Recurse -Force "{nested}"\n'
            f'  macOS/Linux: cp -rn "{nested}/." "{proj}/" && rm -rf "{nested}"')
    extra = [n for n in (os.listdir(proj) if os.path.isdir(proj) else []) if n not in ("assets", ".godot")]
    if extra:
        raise RuntimeError(
            f"{proj} is not a Godot project (no project.godot) and holds other files ({', '.join(sorted(extra)[:5])}). "
            f"Point export.godot_project at your game's folder, or at a new folder for forge to create.")

    def copy_new(src, dst):
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
    shutil.copytree(GODOT_TEMPLATE, proj, dirs_exist_ok=True, copy_function=copy_new)
    print(f"[forge] created Godot project {proj} from godot_template/")
    return proj


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
        prompt = c.get("prompt")
        if not prompt and c.get("subject"):
            # a side view the fitter can measure (see fit_reference.REFERENCE_PROMPT)
            sys.path.insert(0, HERE)
            import fit_reference  # noqa: E402  (same folder)
            prompt = fit_reference.REFERENCE_PROMPT.format(animal=c["subject"])
        why = ""
        if c.get("tool") == "banana" and shutil.which("uv") and os.path.exists(BANANA):
            cmd = ["uv", "run", BANANA, "-p", prompt or self.name, "-f", out, "-m", c.get("model", "nano-banana-2")]
            if c.get("aspect") or c.get("subject"):
                cmd += ["-a", c.get("aspect", "3:2")]
            for ref in c.get("style_refs", []):
                cmd += ["-i", self.src(ref)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0 and os.path.exists(out):
                if c.get("auto_approve"):
                    return out, "generated with Nano Banana (auto-approved)"
                raise ManualStep(f"Reference generated at {out}. Check it against the pass list in the "
                                 f"runbook (full body, arms apart, open hands, flat light; for a fitted creature: "
                                 f"a clean side view with all four legs visible). Regenerate or edit if "
                                 f"needed, then re-run forge.")
            # Usually missing credentials: fall back to the manual step instead of failing.
            err = (proc.stderr or proc.stdout).strip().splitlines()
            last = err[-1] if err else "unknown error"
            hint = "" if "GEMINI_API_KEY" in last else (" Set GEMINI_API_KEY (free key: "
                                                        "https://aistudio.google.com/apikey) to generate it automatically.")
            why = f"Nano Banana couldn't run ({last}).{hint}\n\n"
        raise ManualStep(why + f"Generate a reference image with this prompt (Nano Banana / Gemini, Flux, "
                         f"Midjourney, Bing Image Creator) and save it as {out}, or set concept.image:\n\n"
                         f"{prompt or '(no prompt in manifest)'}")

    def fit_reference(self, g, cfg):
        """Fit build_lowpoly_creature to the reference: work/fit.json, reused on re-runs."""
        spec = g["fit_reference"] if isinstance(g["fit_reference"], dict) else {}
        fit_path = self.p("work", "fit.json")
        sys.path.insert(0, HERE)
        import fit_reference  # noqa: E402  (same folder)
        handoff = self.p("handoff", "fit_keypoints.json")
        keypoints = self.src(spec["keypoints"]) if spec.get("keypoints") else (handoff if os.path.exists(handoff) else None)
        image = self.src(spec["image"]) if spec.get("image") else self.out("concept")
        preset = cfg.get("preset", "wolf")
        model = spec.get("model", os.environ.get("FIT_MODEL", fit_reference.DEFAULT_MODEL))
        animal = spec.get("animal") or (self.m.get("concept") or {}).get("subject")

        def digest(path):
            if not path or not os.path.exists(path):
                return None
            import hashlib
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        # reuse a fit only if it came from the same image, keypoints, preset, model and animal
        inputs = {"image": digest(image), "keypoints": digest(keypoints), "preset": preset,
                  "model": None if keypoints else model, "animal": None if keypoints else animal}
        if os.path.exists(fit_path):
            with open(fit_path) as fh:
                cached = json.load(fh)
            if cached.get("inputs") == inputs:
                return cached
        if not keypoints and not (image and os.path.exists(image)):
            raise ManualStep(f"Fitting needs a side-view reference: add a concept section (e.g. "
                             f'{{"tool": "banana", "subject": "horse"}}), set generate.fit_reference.image, or save '
                             f"hand-placed joints as {handoff} (format: `python pipeline3d/fit_reference.py --schema`).")
        try:
            rep = fit_reference.run(image=image, preset=preset, keypoints=keypoints, animal=animal, model=model,
                                    overlay=self.p("work", "fit_overlay.svg") if image else None)
        except fit_reference.NoKey:
            raise ManualStep(f"Fitting the creature to {image or 'the reference'} needs GEMINI_API_KEY "
                             f"(free key: https://aistudio.google.com/apikey). Set it and re-run forge, or mark the "
                             f"joints yourself: save {handoff} in the format printed by "
                             f"`python pipeline3d/fit_reference.py --schema` (example: manifests/horse_keypoints.json).") from None
        rep["inputs"] = inputs
        with open(fit_path, "w") as fh:
            json.dump(rep, fh, indent=1)
        return rep

    def generate(self):
        g = self.m["generate"]
        raw = self.p("incoming", f"{self.name}_raw.glb")
        if g.get("procedural"):
            cfg = dict(g.get("config", {}))
            cfg["export_path"] = raw
            cfg.setdefault("clear_scene", True)
            fit = None
            if g.get("fit_reference"):
                fit = self.fit_reference(g, cfg)
                cfg["overrides"] = {**fit["overrides"], **(cfg.get("overrides") or {})}   # manifest wins
            rep = _blender(g["procedural"], cfg, self.workdir, "generate")
            if fit:
                rep["fit"] = {k: fit.get(k) for k in ("source", "stance", "warnings", "overlay")}
            return raw, rep
        if g.get("file"):
            # Keep the original format: cleanup picks its importer from the extension
            src = self.src(g["file"])
            raw = os.path.splitext(raw)[0] + os.path.splitext(src)[1].lower()
            shutil.copy2(src, raw)
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
        return rep.get("out", raw), rep       # gen3d renames the file if the result is FBX/OBJ

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
            rep = _blender("quadruped_rig.py", cfg, self.workdir, "rig")
            rep["bend_test"] = self.bend_test(out, r.get("bend_test", True))
            return out, rep
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
            rep = _gen3d(args)
            return rep.get("out", out), rep
        raise ValueError(f"unknown rig method {method}")

    def bend_test(self, rigged, spec):
        """Bend each leg joint to 90 deg and check the skin keeps its thickness (bend_test.py).
        Reports a warning; rig.bend_test: {"strict": true} makes a failing joint stop the build."""
        if spec is False:
            return "skipped"
        spec = spec if isinstance(spec, dict) else {}
        cfg = {"import_path": rigged, "min_retention": spec.get("min_retention", 0.85)}
        try:
            rep = _blender("bend_test.py", cfg, self.workdir, "bend_test")
        except RuntimeError as exc:
            # _blender treats ok=false as a failure; read the report from the log instead
            log = open(os.path.join(self.workdir, ".forge", "bend_test.log")).read()
            found = re.findall(r"^PIPELINE_RESULT (.*)$", log, re.M)
            rep = json.loads(found[-1]) if found else {"ok": False, "error": str(exc)}
        summary = {k: rep.get(k) for k in ("ok", "worst_joint", "worst_retention", "failed", "joints", "error")}
        if not rep.get("ok"):
            msg = (f"bend test: {', '.join(rep.get('failed') or []) or rep.get('error')} "
                   f"collapse when bent 90 deg (worst {rep.get('worst_joint')} {rep.get('worst_retention')}, "
                   f"needs {cfg['min_retention']})")
            print(f"[forge] WARNING {msg}")
            if spec.get("strict"):
                raise RuntimeError(msg)
        return summary

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
        if proj:
            ensure_godot_project(os.path.expanduser(self.src(proj)))
        cfg = {"import_path": src, "export_path": out, "collision": e.get("collision"),
               "copy_to": os.path.join(os.path.expanduser(self.src(proj)), e.get("assets_dir", "assets")) if proj else None}
        return out, _blender("export_for_godot.py", cfg, self.workdir, "export")

    def godot(self):
        proj = (self.m.get("export") or {}).get("godot_project")
        if not proj:
            return None, "skipped (no export.godot_project)"
        proj = os.path.expanduser(self.src(proj))
        ensure_godot_project(proj)
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

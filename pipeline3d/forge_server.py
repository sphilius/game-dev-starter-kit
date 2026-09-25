# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
forge_server.py - local HTTP API around forge.py, for the Forge Studio app (or any client).

    python pipeline3d/forge_server.py                    # http://127.0.0.1:8765, prints a token
    FORGE_TOKEN=secret python pipeline3d/forge_server.py --port 8765

It runs on the machine that has Blender and Godot. Clients never send file paths or
scripts: they send a manifest, the server checks it against a whitelist, saves it under
pipeline3d/requests/, and runs forge in a single background worker (Blender jobs are
heavy, so they run one at a time). Manual steps (concept image, Mixamo rig, clips) are
completed by uploading the file, then resuming.

API (JSON; every call except /api/health needs "Authorization: Bearer <token>"):
    GET  /api/health                        tools found, API keys present, Godot project
    GET  /api/examples                      the example manifests (for the chat model's context)
    GET  /api/assets                        every asset with status
    POST /api/assets        {manifest}      validate, save, queue          -> 202
    GET  /api/assets/<name>                 state, manifest, instructions, previews, log tail
    POST /api/assets/<name>/resume          queue again (after a manual step)
    POST /api/assets/<name>/upload?slot=concept|model|rigged|clip&filename=x.ext   raw body
    GET  /api/assets/<name>/files/<previews|export|handoff>/<file>   previews, final GLB, file to rig

Environment: FORGE_TOKEN, FORGE_GODOT_PROJECT (default ~/pipeline3d_game), BLENDER, GODOT,
TRIPO_API_KEY / MESHY_API_KEY / RODIN_API_KEY (passed through to forge).
"""

import argparse
import hmac
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
FORGE = os.path.join(HERE, "forge.py")
BLENDER_DIR = os.path.join(HERE, "blender")
REQUESTS = os.path.join(HERE, "requests")
UPLOADS = os.path.join(HERE, "uploads")
BUILD = os.path.join(HERE, "build")
EXAMPLES = os.path.join(HERE, "manifests")
MAX_UPLOAD = 200 * 1024 * 1024

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,99}$")
ENUMS = {
    ("generate", "provider"): {"tripo", "meshy", "rodin"},
    ("generate", "mode"): {"text", "image", "multiview"},
    ("rig", "method"): {"none", "quadruped", "mixamo", "accurig", "manual", "tripo", "meshy"},
    ("animations", "method"): {"none", "procedural", "clips_dir", "tripo", "meshy"},
    ("export", "collision"): {None, "convex", "trimesh"},
}
PREVIEW_VIEWS = ["front", "side", "three_quarter"]


class BadRequest(Exception):
    pass


# ----------------------------------------------------------------------------- manifest checks

def _scalar_tree(value, depth=0):
    """Options must be plain JSON data (no deep nesting)."""
    if depth > 4:
        raise BadRequest("options nested too deeply")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str) or len(k) > 60:
                raise BadRequest("bad option key")
            _scalar_tree(v, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _scalar_tree(v, depth + 1)
    elif not isinstance(value, (str, int, float, bool)) and value is not None:
        raise BadRequest("options must be JSON values")


def sanitize_manifest(m, godot_project):
    """Whitelist a manifest from the network. Paths only ever point inside this server's folders."""
    if not isinstance(m, dict):
        raise BadRequest("manifest must be an object")
    name = str(m.get("name", "")).strip().lower()
    if not NAME_RE.match(name):
        raise BadRequest("name must be lowercase letters, digits or _, starting with a letter (max 40)")
    out = {"name": name, "kind": str(m.get("kind", ""))[:40], "notes": str(m.get("notes", ""))[:500]}
    upload_dir = os.path.join(UPLOADS, name)

    def upload_path(filename, what):
        if not isinstance(filename, str) or not FILE_RE.match(filename) or ".." in filename:
            raise BadRequest(f"{what} must be a plain file name uploaded to this asset")
        path = os.path.join(upload_dir, filename)
        if not os.path.exists(path):
            raise BadRequest(f"{what} '{filename}' has not been uploaded yet")
        return path

    c = m.get("concept")
    if c:
        if not isinstance(c, dict):
            raise BadRequest("concept must be an object")
        concept = {"prompt": str(c.get("prompt", ""))[:2000],
                   "out": f"{name}_ref.png"}
        if c.get("tool") in ("banana", "manual"):
            concept["tool"] = c["tool"]
        if c.get("image"):
            concept["image"] = upload_path(c["image"], "concept.image")
        out["concept"] = concept

    g = m.get("generate")
    if not isinstance(g, dict):
        raise BadRequest("generate is required")
    if g.get("procedural"):
        script = str(g["procedural"])
        if not re.match(r"^build_[a-z_]+\.py$", script) or not os.path.exists(os.path.join(BLENDER_DIR, script)):
            raise BadRequest(f"unknown procedural script {script}")
        cfg = g.get("config", {}) or {}
        _scalar_tree(cfg)
        cfg = {k: v for k, v in cfg.items() if k not in ("export_path", "import_path")}
        out["generate"] = {"procedural": script, "config": cfg}
    elif g.get("file"):
        out["generate"] = {"file": upload_path(g["file"], "generate.file")}
    else:
        gen = {"provider": g.get("provider"), "mode": g.get("mode", "image")}
        for key in ("provider", "mode"):
            if gen[key] not in ENUMS[("generate", key)]:
                raise BadRequest(f"generate.{key} must be one of {sorted(ENUMS[('generate', key)])}")
        if g.get("prompt"):
            gen["prompt"] = str(g["prompt"])[:2000]
        if g.get("image"):
            gen["image"] = upload_path(g["image"], "generate.image")
        opts = g.get("options", {}) or {}
        _scalar_tree(opts)
        gen["options"] = opts
        out["generate"] = gen

    cl = m.get("cleanup", {})
    if cl is False:
        out["cleanup"] = False
    else:
        cl = cl or {}
        allowed = {"target_tris": int, "target_height_m": (int, float, type(None)), "origin": str,
                   "remove_floaters_below": (int, float), "merge_distance": (int, float),
                   "fill_holes_sides": int, "smooth_shading": bool, "pack_uvs": bool}
        clean = {}
        for k, v in cl.items():
            if k in allowed and isinstance(v, allowed[k]):
                clean[k] = v
        if clean.get("origin") and clean["origin"] not in ("FEET", "CENTER", "KEEP"):
            raise BadRequest("cleanup.origin must be FEET, CENTER or KEEP")
        out["cleanup"] = clean

    r = m.get("rig") or {"method": "none"}
    if r.get("method") not in ENUMS[("rig", "method")]:
        raise BadRequest(f"rig.method must be one of {sorted(ENUMS[('rig', 'method')])}")
    rig = {"method": r["method"]}
    if r.get("clip_prefix"):
        rig["clip_prefix"] = re.sub(r"[^a-z0-9_]", "", str(r["clip_prefix"]).lower())[:20]
    for key in ("config", "options"):
        if r.get(key):
            _scalar_tree(r[key])
            rig[key] = {k: v for k, v in r[key].items() if k not in ("export_path", "import_path")}
    out["rig"] = rig

    a = m.get("animations") or {"method": "procedural" if rig["method"] == "quadruped" else "none"}
    if a.get("method") not in ENUMS[("animations", "method")]:
        raise BadRequest(f"animations.method must be one of {sorted(ENUMS[('animations', 'method')])}")
    anim = {"method": a["method"]}
    for key in ("expect", "rename", "clips", "strip_root_motion", "hips_bone"):
        if key in a:
            _scalar_tree(a[key])
            anim[key] = a[key]
    out["animations"] = anim

    e = m.get("export") or {}
    if e.get("collision") not in ENUMS[("export", "collision")]:
        raise BadRequest("export.collision must be null, convex or trimesh")
    out["export"] = {"collision": e.get("collision"), "godot_project": godot_project}
    return out


# ----------------------------------------------------------------------------- jobs

class Forge:
    def __init__(self, godot_project):
        self.godot_project = godot_project
        self.jobs = {}               # name -> {"status", "queued_at", ...}
        self.q = queue.Queue()
        self.lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True).start()

    def enqueue(self, name):
        with self.lock:
            job = self.jobs.get(name)
            if job and job["status"] in ("queued", "running"):
                return job
            self.jobs[name] = {"status": "queued", "queued_at": time.time()}
        self.q.put(name)
        return self.jobs[name]

    def _worker(self):
        while True:
            name = self.q.get()
            with self.lock:
                self.jobs[name].update(status="running", started_at=time.time())
            workdir = os.path.join(BUILD, name)
            os.makedirs(workdir, exist_ok=True)
            log_path = os.path.join(workdir, "forge_server.log")
            with open(log_path, "a") as log:
                log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} forge {name}\n")
                log.flush()
                proc = subprocess.run([sys.executable, FORGE, os.path.join(REQUESTS, f"{name}.json")],
                                      stdout=log, stderr=subprocess.STDOUT)
            status = {0: "done", 3: "waiting"}.get(proc.returncode, "error")
            if status == "done":
                try:
                    self._previews(name)
                except Exception as exc:  # noqa: BLE001 - previews are best effort
                    with open(log_path, "a") as log:
                        log.write(f"[server] preview render failed: {exc}\n")
            with self.lock:
                self.jobs[name].update(status=status, finished_at=time.time(), exit_code=proc.returncode)

    def _previews(self, name):
        glb = os.path.join(BUILD, name, "export", f"{name}.glb")
        blender = os.environ.get("BLENDER") or shutil.which("blender")
        if not (blender and os.path.exists(glb)):
            return
        out_dir = os.path.join(BUILD, name, "previews")
        subprocess.run([blender, "-b", "--factory-startup", "-P", os.path.join(BLENDER_DIR, "render_preview.py"), "--",
                        f"import_path={json.dumps(glb)}", "clear_scene=true", f"out_dir={json.dumps(out_dir)}",
                        f"prefix={json.dumps(name)}", f"views={json.dumps(PREVIEW_VIEWS)}", "resolution=512"],
                       capture_output=True, timeout=300)

    def status(self, name):
        workdir = os.path.join(BUILD, name)
        state_path = os.path.join(workdir, "forge_state.json")
        state = json.load(open(state_path)) if os.path.exists(state_path) else {}
        job = dict(self.jobs.get(name, {}))
        if not job:
            if any(s.get("status") == "error" for s in state.values()):
                job["status"] = "error"
            elif any(s.get("status") == "waiting" for s in state.values()):
                job["status"] = "waiting"
            elif state.get("godot", {}).get("status") == "done" or state.get("export", {}).get("status") == "done":
                job["status"] = "done"
            else:
                job["status"] = "new"
        stages = {k: v.get("status") for k, v in state.items()}
        waiting = next((v.get("instructions") for v in state.values() if v.get("status") == "waiting"), None)
        error = next((v.get("error") for v in state.values() if v.get("status") == "error"), None)
        prev_dir = os.path.join(workdir, "previews")
        previews = sorted(f for f in os.listdir(prev_dir) if f.endswith(".png")) if os.path.isdir(prev_dir) else []
        glb = os.path.join(workdir, "export", f"{name}.glb")
        hand_dir = os.path.join(workdir, "handoff")
        handoff = sorted(f for f in os.listdir(hand_dir)) if os.path.isdir(hand_dir) else []
        log_path = os.path.join(workdir, "forge_server.log")
        log_tail = open(log_path).read()[-3000:] if os.path.exists(log_path) else ""
        manifest_path = os.path.join(REQUESTS, f"{name}.json")
        return {
            "name": name, **job, "stages": stages, "instructions": _strip_paths(waiting), "error": _strip_paths(error),
            "previews": [f"previews/{p}" for p in previews],
            "export": f"export/{name}.glb" if os.path.exists(glb) else None,
            "handoff": [f"handoff/{f}" for f in handoff],
            "report": {k: v.get("report") for k, v in state.items() if isinstance(v.get("report"), dict)},
            "manifest": json.loads(_strip_paths(open(manifest_path).read())) if os.path.exists(manifest_path) else None,
            "log_tail": _strip_paths(log_tail),
        }


def _strip_paths(text):
    """Don't leak the server's absolute paths to clients."""
    if not text:
        return text
    return (text.replace(UPLOADS + os.sep, "").replace(HERE + os.sep, "pipeline3d/")
            .replace(os.path.expanduser("~"), "~"))


# ----------------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "ForgeServer/1.0"
    forge = None
    token = ""
    origins = "*"

    def log_message(self, fmt, *args):
        sys.stderr.write("[forge_server] " + (fmt % args) + "\n")

    # --- helpers
    def _cors(self):
        origin = self.headers.get("Origin", "")
        allowed = self.origins
        if allowed == "*" or origin in allowed.split(","):
            self.send_header("Access-Control-Allow-Origin", origin or "*")
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        # Chrome's Private Network Access: allow https pages (AI Studio, Cloud Run) to call localhost
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _json(self, code, obj):
        body = json.dumps(obj, indent=1, default=str).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        got = self.headers.get("Authorization", "")
        if got.startswith("Bearer ") and hmac.compare_digest(got[7:].encode(), self.token.encode()):
            return True
        self._json(401, {"ok": False, "error": "missing or wrong token (Authorization: Bearer <FORGE_TOKEN>)"})
        return False

    def _body(self, limit=1024 * 1024):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise BadRequest(f"body too large (max {limit // 1024 // 1024} MB)")
        return self.rfile.read(length)

    # --- verbs
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/")]
        try:
            if parts == ["api", "health"]:
                return self._json(200, self._health())
            if not self._authorized():
                return None
            if parts == ["api", "examples"]:
                ex = {}
                for f in sorted(os.listdir(EXAMPLES)):
                    if f.endswith(".json"):
                        ex[f[:-5]] = json.load(open(os.path.join(EXAMPLES, f)))
                return self._json(200, ex)
            if parts == ["api", "assets"]:
                names = sorted({f[:-5] for f in os.listdir(REQUESTS) if f.endswith(".json")}) if os.path.isdir(REQUESTS) else []
                return self._json(200, [{k: v for k, v in self.forge.status(n).items()
                                         if k in ("name", "status", "stages", "previews", "export")} for n in names])
            if len(parts) == 3 and parts[:2] == ["api", "assets"]:
                self._check_name(parts[2])
                return self._json(200, self.forge.status(parts[2]))
            if len(parts) == 6 and parts[:2] == ["api", "assets"] and parts[3] == "files":
                return self._file(parts[2], parts[4], parts[5])
            return self._json(404, {"ok": False, "error": "not found"})
        except BadRequest as exc:
            return self._json(400, {"ok": False, "error": str(exc)})

    def do_POST(self):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/")]
        try:
            if not self._authorized():
                return None
            if parts == ["api", "assets"]:
                data = json.loads(self._body() or b"{}")
                manifest = sanitize_manifest(data.get("manifest", data), self.forge.godot_project)
                os.makedirs(REQUESTS, exist_ok=True)
                with open(os.path.join(REQUESTS, f"{manifest['name']}.json"), "w") as fh:
                    json.dump(manifest, fh, indent=1)
                if data.get("restart"):
                    state = os.path.join(BUILD, manifest["name"], "forge_state.json")
                    if os.path.exists(state):
                        os.remove(state)
                job = self.forge.enqueue(manifest["name"])
                return self._json(202, {"ok": True, "name": manifest["name"], "status": job["status"]})
            if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "resume":
                self._check_name(parts[2], must_exist=True)
                job = self.forge.enqueue(parts[2])
                return self._json(202, {"ok": True, "name": parts[2], "status": job["status"]})
            if len(parts) == 4 and parts[:2] == ["api", "assets"] and parts[3] == "upload":
                return self._upload(parts[2], parse_qs(url.query))
            return self._json(404, {"ok": False, "error": "not found"})
        except (BadRequest, ValueError) as exc:
            return self._json(400, {"ok": False, "error": str(exc)})

    # --- endpoints
    def _health(self):
        blender = os.environ.get("BLENDER") or shutil.which("blender")
        godot = os.environ.get("GODOT") or shutil.which("godot")
        return {"ok": True, "blender": bool(blender and os.path.exists(blender)),
                "godot": bool(godot and os.path.exists(godot)),
                "godot_project": _strip_paths(self.forge.godot_project),
                "godot_project_exists": os.path.exists(os.path.join(self.forge.godot_project, "project.godot")),
                "keys": {p: bool(os.environ.get(f"{p.upper()}_API_KEY")) for p in ("tripo", "meshy", "rodin")},
                "google_image": bool(os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT"))}

    def _check_name(self, name, must_exist=False):
        if not NAME_RE.match(name):
            raise BadRequest("bad asset name")
        if must_exist and not os.path.exists(os.path.join(REQUESTS, f"{name}.json")):
            raise BadRequest(f"no asset named {name}")

    def _upload(self, name, query):
        self._check_name(name)
        slot = (query.get("slot") or [""])[0]
        filename = (query.get("filename") or [""])[0]
        if not FILE_RE.match(filename) or ".." in filename:
            raise BadRequest("filename must be a plain file name")
        ext = os.path.splitext(filename)[1].lower()
        allowed = {"concept": {".png", ".jpg", ".jpeg", ".webp"}, "model": {".glb", ".gltf", ".fbx", ".obj"},
                   "rigged": {".fbx"}, "clip": {".fbx", ".glb"}}
        if slot not in allowed or ext not in allowed[slot]:
            raise BadRequest(f"slot must be one of {sorted(allowed)} with a matching file type")
        data = self._body(MAX_UPLOAD)
        workdir = os.path.join(BUILD, name)
        dest = {
            "concept": os.path.join(workdir, "refs", f"{name}_ref.png"),
            "model": os.path.join(UPLOADS, name, filename),
            "rigged": os.path.join(workdir, "incoming", f"{name}_rigged.fbx"),
            "clip": os.path.join(workdir, "incoming", "clips", filename),
        }[slot]
        if slot == "concept" and ext != ".png":
            dest = os.path.join(UPLOADS, name, filename)   # non-PNG: reference it as concept.image instead
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        return self._json(200, {"ok": True, "slot": slot, "saved_as": os.path.basename(dest), "bytes": len(data)})

    def _file(self, name, folder, filename):
        self._check_name(name)
        if folder not in ("previews", "export", "handoff") or not FILE_RE.match(filename) or ".." in filename:
            raise BadRequest("bad file path")
        path = os.path.join(BUILD, name, folder, filename)
        if not os.path.isfile(path):
            return self._json(404, {"ok": False, "error": "no such file"})
        ctype = {".png": "image/png", ".glb": "model/gltf-binary"}.get(os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to allow your phone on the same Wi-Fi")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FORGE_PORT", "8765")))
    ap.add_argument("--origins", default=os.environ.get("FORGE_ALLOWED_ORIGINS", "*"),
                    help="comma-separated browser origins allowed by CORS (default *; the token still applies)")
    a = ap.parse_args(argv)

    token = os.environ.get("FORGE_TOKEN") or secrets.token_urlsafe(18)
    godot_project = os.path.abspath(os.path.expanduser(os.environ.get("FORGE_GODOT_PROJECT", "~/pipeline3d_game")))
    for d in (REQUESTS, UPLOADS, BUILD):
        os.makedirs(d, exist_ok=True)
    Handler.forge = Forge(godot_project)
    Handler.token = token
    Handler.origins = a.origins
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"[forge_server] http://{a.host}:{a.port}   Godot project: {godot_project}")
    if not os.environ.get("FORGE_TOKEN"):
        print(f"[forge_server] token (set FORGE_TOKEN to fix it): {token}")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

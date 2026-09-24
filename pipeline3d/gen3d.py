# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
gen3d.py - one CLI for cloud 3D generation, rigging and animation APIs.

Providers (bring your own key; all have free credits or a free tier):
  tripo   TRIPO_API_KEY    text/image/multiview -> model, quad/low-poly options, auto-rig, retarget
  meshy   MESHY_API_KEY    text/image -> model, remesh, humanoid auto-rig, animation library
  rodin   RODIN_API_KEY    Hyper3D Rodin text/image -> model (Quad mesh mode, Gen-2 tier)

Commands (every command prints one JSON object on stdout):
  create    --provider P --mode text|image|multiview [--prompt ..] [--image f ..] [--opt k=v ..]
  status    --provider P --task ID
  wait      --provider P --task ID [--timeout 1200]
  download  --provider P --task ID --out file.glb [--prefer pbr_model|model|fbx ..]
  run       create + wait + download in one go (same flags as create, plus --out)
  rig       --provider tripo|meshy --task MODEL_TASK_ID [--out rigged.glb] [--opt ..]
  animate   --provider tripo|meshy --task RIG_TASK_ID --animation preset:walk|<meshy action id> [--out clip.glb]
  balance   --provider P

--opt values are parsed as JSON when possible (quad=true face_limit=15000 texture=false).
The option names are the providers' own request fields, passed through unchanged, so new
API options work without touching this script. Check the provider docs for current names:
  https://platform.tripo3d.ai/docs   https://docs.meshy.ai   https://developer.hyper3d.ai

Examples:
  uv run gen3d.py run --provider tripo --mode image --image refs/body_front.png \\
      --opt face_limit=15000 --opt quad=true --out incoming/character_raw.glb
  uv run gen3d.py run --provider meshy --mode text --prompt "low poly wooden crate" --out incoming/crate.glb
"""

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

TIMEOUT = 60


# ----------------------------------------------------------------------------- HTTP

def _request(method, url, headers=None, body=None, content_type="application/json"):
    headers = dict(headers or {})
    data = None
    if body is not None:
        if content_type == "application/json":
            data = json.dumps(body).encode()
        else:
            data = body
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:800]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from None
    try:
        return json.loads(raw)
    except ValueError:
        return {"raw": raw.decode(errors="replace")[:800]}


def _multipart(fields, files):
    """fields: {name: str}, files: [(name, path)] -> (body, content_type)"""
    boundary = uuid.uuid4().hex
    out = bytearray()
    for name, value in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    for name, path in files:
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            payload = fh.read()
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: {mime}\r\n\r\n").encode()
        out += payload + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _download(url, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as resp, open(out, "wb") as fh:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    return os.path.getsize(out)


def _find_urls(obj, path=""):
    """Every http(s) URL in a nested response, with its key path (e.g. output.pbr_model)."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found += _find_urls(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _find_urls(v, f"{path}[{i}]")
    elif isinstance(obj, str) and obj.startswith(("http://", "https://")):
        found.append((path, obj))
    return found


def _pick_url(urls, prefer, ext):
    model_urls = [(p, u) for p, u in urls if any(x in u.split("?")[0].lower() for x in (".glb", ".fbx", ".obj", ".gltf", ".usdz", ".zip"))]
    for key in prefer:
        for p, u in model_urls:
            if key in p:
                return p, u
    for p, u in model_urls:
        if u.split("?")[0].lower().endswith("." + ext):
            return p, u
    return model_urls[0] if model_urls else (None, None)


def _key(name):
    val = os.environ.get(name)
    if not val:
        # RuntimeError, not SystemExit: the MCP server imports this module and must survive it
        raise RuntimeError(f"set {name} in your environment (see the provider's dashboard for a key)")
    return val


# ----------------------------------------------------------------------------- providers

class Tripo:
    base = "https://api.tripo3d.ai/v2/openapi"
    done = {"success"}
    failed = {"failed", "cancelled", "banned", "expired", "unknown"}

    def __init__(self):
        self.h = {"Authorization": f"Bearer {_key('TRIPO_API_KEY')}"}

    def _upload(self, path):
        body, ctype = _multipart({}, [("file", path)])
        r = _request("POST", f"{self.base}/upload", self.h, body, ctype)
        token = (r.get("data") or {}).get("image_token") or (r.get("data") or {}).get("file_token")
        if not token:
            raise RuntimeError(f"upload failed: {r}")
        ext = os.path.splitext(path)[1].lstrip(".").lower().replace("jpeg", "jpg")
        return {"type": ext, "file_token": token}

    def _task(self, payload):
        r = _request("POST", f"{self.base}/task", self.h, payload)
        tid = (r.get("data") or {}).get("task_id")
        if not tid:
            raise RuntimeError(f"task create failed: {r}")
        return tid

    def create(self, mode, prompt, images, opts):
        if mode == "text":
            payload = {"type": "text_to_model", "prompt": prompt}
        elif mode == "image":
            payload = {"type": "image_to_model", "file": self._upload(images[0])}
        elif mode == "multiview":   # order: front, left, back, right
            payload = {"type": "multiview_to_model", "files": [self._upload(p) for p in images]}
        else:
            raise ValueError(mode)
        payload.update(opts)
        return self._task(payload)

    def rig(self, task, opts):
        return self._task({"type": "animate_rig", "original_model_task_id": task, "out_format": "glb", **opts})

    def animate(self, task, animation, opts):
        return self._task({"type": "animate_retarget", "original_model_task_id": task,
                           "animation": animation, "out_format": "glb", **opts})

    def status(self, task):
        data = _request("GET", f"{self.base}/task/{task}", self.h).get("data", {})
        return {"state": data.get("status"), "progress": data.get("progress"), "raw": data}

    def balance(self):
        return _request("GET", f"{self.base}/user/balance", self.h)


class Meshy:
    base = "https://api.meshy.ai/openapi"
    done = {"SUCCEEDED"}
    failed = {"FAILED", "CANCELED", "EXPIRED"}
    # task ids are stored as "<endpoint>:<id>" so status knows where to look
    endpoints = {"text": "v2/text-to-3d", "image": "v1/image-to-3d", "multiview": "v1/multi-image-to-3d",
                 "rig": "v1/rigging", "animate": "v1/animations", "remesh": "v1/remesh"}

    def __init__(self):
        self.h = {"Authorization": f"Bearer {_key('MESHY_API_KEY')}"}

    @staticmethod
    def _data_uri(path):
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as fh:
            return f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"

    def _post(self, kind, payload):
        r = _request("POST", f"{self.base}/{self.endpoints[kind]}", self.h, payload)
        tid = r.get("result")
        if not tid:
            raise RuntimeError(f"{kind} create failed: {r}")
        return f"{kind}:{tid}"

    def create(self, mode, prompt, images, opts):
        if mode == "text":
            payload = {"mode": "preview", "prompt": prompt, **opts}
        elif mode == "image":
            src = images[0]
            payload = {"image_url": src if src.startswith("http") else self._data_uri(src), **opts}
        elif mode == "multiview":
            payload = {"image_urls": [p if p.startswith("http") else self._data_uri(p) for p in images], **opts}
        elif mode == "refine":        # text-to-3d second pass: --prompt carries the preview task id
            payload = {"mode": "refine", "preview_task_id": prompt.split(":")[-1], **opts}
            mode = "text"
        else:
            raise ValueError(mode)
        return self._post(mode, payload)

    def rig(self, task, opts):
        kind, _, tid = task.rpartition(":")
        src = {"model_url": tid} if tid.startswith("http") else {"input_task_id": tid}
        return self._post("rig", {**src, **opts})

    def animate(self, task, animation, opts):
        return self._post("animate", {"rig_task_id": task.rpartition(":")[2], "action_id": int(animation), **opts})

    def status(self, task):
        kind, _, tid = task.partition(":")
        data = _request("GET", f"{self.base}/{self.endpoints[kind]}/{tid}", self.h)
        return {"state": data.get("status"), "progress": data.get("progress"), "raw": data}

    def balance(self):
        return _request("GET", f"{self.base}/v1/balance", self.h)


class Rodin:
    base = "https://hyperhuman.deemos.com/api/v2"
    done = {"Done"}
    failed = {"Failed"}

    def __init__(self):
        self.h = {"Authorization": f"Bearer {_key('RODIN_API_KEY')}"}

    def create(self, mode, prompt, images, opts):
        fields = {"tier": "Gen-2", "mesh_mode": "Quad", "geometry_file_format": "glb", "material": "PBR"}
        fields.update({k: (json.dumps(v) if isinstance(v, (list, dict)) else str(v)) for k, v in opts.items()})
        if prompt:
            fields["prompt"] = prompt
        files = [("images", p) for p in (images or [])]
        body, ctype = _multipart(fields, files)
        r = _request("POST", f"{self.base}/rodin", self.h, body, ctype)
        if not r.get("uuid"):
            raise RuntimeError(f"rodin create failed: {r}")
        return f"{r['uuid']}|{r['jobs']['subscription_key']}"

    def status(self, task):
        _, key = task.split("|", 1)
        jobs = _request("POST", f"{self.base}/status", self.h, {"subscription_key": key}).get("jobs", [])
        states = [j.get("status") for j in jobs]
        state = "Failed" if "Failed" in states else ("Done" if states and all(s == "Done" for s in states) else "Generating")
        return {"state": state, "progress": states, "raw": {"jobs": jobs}}

    def result(self, task):
        uid, _ = task.split("|", 1)
        return _request("POST", f"{self.base}/download", self.h, {"task_uuid": uid})

    def rig(self, task, opts):
        raise RuntimeError("rodin has no rig endpoint; use tripo/meshy, Mixamo/AccuRIG or quadruped_rig.py")

    animate = rig

    def balance(self):
        return _request("GET", f"{self.base}/check_balance", self.h)


PROVIDERS = {"tripo": Tripo, "meshy": Meshy, "rodin": Rodin}


# ----------------------------------------------------------------------------- commands

def _wait(p, task, timeout, quiet=False):
    start = time.time()
    delay = 3
    while True:
        st = p.status(task)
        if not quiet:
            print(f"[gen3d] {task}: {st['state']} {st.get('progress') or ''}", file=sys.stderr)
        if st["state"] in p.done:
            return st
        if st["state"] in p.failed:
            raise RuntimeError(f"task {task} ended {st['state']}: {json.dumps(st['raw'])[:600]}")
        if time.time() - start > timeout:
            raise TimeoutError(f"task {task} still {st['state']} after {timeout}s")
        time.sleep(delay)
        delay = min(delay * 1.5, 20)


def _download_result(p, task, out, prefer):
    raw = p.result(task) if isinstance(p, Rodin) else p.status(task)["raw"]
    ext = os.path.splitext(out)[1].lstrip(".").lower() or "glb"
    path, url = _pick_url(_find_urls(raw), prefer, ext)
    if not url:
        raise RuntimeError(f"no model URL in result: {json.dumps(raw)[:600]}")
    size = _download(url, out)
    sidecar = {"provider": type(p).__name__.lower(), "task": task, "source_field": path, "bytes": size}
    with open(out + ".gen3d.json", "w") as fh:
        json.dump(sidecar, fh, indent=1)
    return {"ok": True, "out": os.path.abspath(out), **sidecar}


def _opts(pairs):
    out = {}
    for pair in pairs or []:
        k, _, v = pair.partition("=")
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["create", "status", "wait", "download", "run", "rig", "animate", "balance"])
    ap.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    ap.add_argument("--mode", default="image", choices=["text", "image", "multiview", "refine"])
    ap.add_argument("--prompt")
    ap.add_argument("--image", action="append", default=[], help="repeat for multiview (front, left, back, right)")
    ap.add_argument("--task")
    ap.add_argument("--animation", help="tripo: preset:walk etc.  meshy: numeric action id")
    ap.add_argument("--out")
    ap.add_argument("--prefer", action="append", default=[],
                    help="result field to prefer when several models are returned (pbr_model, model, fbx...)")
    ap.add_argument("--opt", action="append", default=[], help="provider request field k=v (JSON-parsed)")
    ap.add_argument("--timeout", type=int, default=1200)
    a = ap.parse_args(argv)

    opts = _opts(a.opt)
    prefer = a.prefer or ["pbr_model", "rigged_character_glb", "animation_glb", "model_urls.glb", "model", "glb"]
    try:
        p = PROVIDERS[a.provider]()
        if a.command == "balance":
            res = {"ok": True, **p.balance()}
        elif a.command == "create":
            res = {"ok": True, "provider": a.provider, "task": p.create(a.mode, a.prompt, a.image, opts)}
        elif a.command == "status":
            st = p.status(a.task)
            res = {"ok": True, "state": st["state"], "progress": st.get("progress"),
                   "urls": [u for u in _find_urls(st["raw"])][:12]}
        elif a.command == "wait":
            st = _wait(p, a.task, a.timeout)
            res = {"ok": True, "state": st["state"]}
        elif a.command == "download":
            res = _download_result(p, a.task, a.out, prefer)
        elif a.command in ("run", "rig", "animate"):
            if not a.out:
                ap.error("--out is required")
            if a.command == "run":
                task = p.create(a.mode, a.prompt, a.image, opts)
            elif a.command == "rig":
                task = p.rig(a.task, opts)
            else:
                task = p.animate(a.task, a.animation, opts)
            print(json.dumps({"provider": a.provider, "task": task}), file=sys.stderr)
            _wait(p, task, a.timeout)
            res = _download_result(p, task, a.out, prefer)
        print(json.dumps(res, indent=1))
        return 0
    except (RuntimeError, TimeoutError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=1))
        return 1


if __name__ == "__main__":
    sys.exit(main())

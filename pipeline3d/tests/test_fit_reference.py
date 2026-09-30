"""
test_fit_reference.py - round trip for fit_reference.py, no API key needed.

For each preset: draw the creature's joints as the keypoints Gemini would return for a side view
(random facing, image size and placement), fit them, rebuild the creature from the fitted
overrides, and check that the rebuilt joints (rig landmarks) land where the originals were, the
mesh is watertight and quadruped_rig skins every vertex. Also runs one fit through a mock Gemini
endpoint (GEMINI_API_BASE) to exercise the request/response path.

    blender -b --factory-startup -P pipeline3d/tests/test_fit_reference.py -- [out_dir]
"""

import importlib.util
import json
import os
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

P3D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, P3D)
import fit_reference as fr  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(P3D, "blender", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _load("build_lowpoly_creature")
rig = _load("quadruped_rig")
OUT = (sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 1
       else os.path.join(os.environ.get("TMPDIR", "/tmp"), "p3d_fit_test"))
os.makedirs(OUT, exist_ok=True)


def keypoints_for(preset, rnd, facing):
    """What a perfect detector would return for this preset seen from the side."""
    p = json.loads(json.dumps(build.PRESETS[preset]))
    p["_leg_base"] = p["leg_len"]
    build._graph(p)
    W, H = rnd.choice([(1536, 1024), (1024, 1024), (1200, 900)])
    ppm = rnd.uniform(500, 900) / max(z for _, z, _ in p["body"])   # pixels per metre
    x0, ground = W / 2 + rnd.uniform(-60, 60), H * 0.9

    def img(y, z):   # builder (head at -Y) -> 0-1000 image coords
        fwd = -y
        x = x0 + fwd * ppm * (1 if facing == "right" else -1)
        return x / W * 1000, (ground - z * ppm) / H * 1000

    def slc(y, z, r, frac=fr.DEPTH_FRAC["body"]):
        x, yc = img(y, z)
        d = r / frac * ppm / H * 1000
        return {"x": x, "top": yc - d / 2, "bottom": yc + d / 2}

    def pt(y, z, r=None):
        x, yy = img(y, z)
        out = {"x": x, "y": yy}
        if r is not None:
            out["width"] = 2 * r * ppm / W * 1000
        return out

    head = p["head"]
    skull = head[1]
    tail, pos = [], (p["body"][0][0], p["body"][0][1])
    for dy, dz, r in p["tail"]:
        pos = (pos[0] + dy, pos[1] + dz)
        tail.append(pt(pos[0], pos[1], r))
    if len(tail) < 2:
        tail.append(pt(pos[0] + 0.02, pos[1] - 0.02, p["tail"][-1][2] * 0.8))
    stance = build.STANCES[p["stance"]]
    legs = {}
    for leg in ("front", "hind"):
        chain = p["_chains"][(leg, 1)]
        legs[leg] = [pt(co[1], co[2], p["leg_r"] * rs) for co, (_, _, rs) in zip(chain, stance[leg])]
    return {
        "is_side_view": True, "facing": facing, "stance": p["stance"], "ground_y": ground / H * 1000,
        "torso": [slc(*j) for j in p["body"]],
        "neck": slc(*head[0]), "skull": slc(*skull), "muzzle": slc(*head[2], frac=fr.DEPTH_FRAC["muzzle"]),
        "nose": pt(head[3][0], head[3][1]),
        "ear_tip": pt(skull[0], skull[1] + skull[2] + p["ears"]),
        "tail": tail[:5], "front_leg": legs["front"], "hind_leg": legs["hind"],
    }, (W, H)


class MockGemini(BaseHTTPRequestHandler):
    payload = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["x-goog-api-key"] == "test-key"
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/png"
        out = {"candidates": [{"content": {"parts": [{"text": json.dumps(MockGemini.payload)}]}}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    rnd = random.Random(7)
    failures = []
    for i, preset in enumerate(["wolf", "boar", "bear", "deer", "cat"]):
        kp, (W, H) = keypoints_for(preset, rnd, ["left", "right"][i % 2])
        rep = fr.fit(kp, preset, W, H)
        # same trunk width as the fit (landmark x is a fraction of the body's width)
        ref = build.main({"preset": preset, "muscle": 0.0, "clear_scene": True,
                          "overrides": {"body_width": fr.PRESET_BASICS[preset]["width"]}})
        glb = os.path.join(OUT, f"{preset}_fitted.glb")
        fitted = build.main({"preset": preset, "muscle": 0.0, "clear_scene": True,
                             "overrides": rep["overrides"], "export_path": glb})
        worst = max(abs(a - b)
                    for bone in ref["landmarks"]
                    for ends in zip(ref["landmarks"][bone], fitted["landmarks"][bone])
                    for a, b in zip(*ends))
        skinned = rig.main({"import_path": glb, "clear_scene": True})
        ok = (worst < 0.02 and fitted["non_manifold"] == 0 and fitted["fitted_legs"]
              and skinned["unweighted_verts"] == 0 and not rep["warnings"])
        print(f"[test] fit {preset:5s} facing {kp['facing']:5s} {W}x{H}: landmark error {worst:.4f}, "
              f"non-manifold {fitted['non_manifold']}, unweighted {skinned['unweighted_verts']}, "
              f"warnings {rep['warnings']} -> {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(preset)

    # a real detector is imprecise: jitter every coordinate by up to 1.5 % of the image and fit
    # with random muscle; the mesh must still be watertight and fully skinned
    def jitter(obj, r):
        if isinstance(obj, dict):
            return {k: (v + r.uniform(-15, 15) if k in ("x", "y", "top", "bottom") else
                        v * r.uniform(0.8, 1.25) if k == "width" else jitter(v, r)) for k, v in obj.items()}
        return [jitter(v, r) for v in obj] if isinstance(obj, list) else obj
    for i, preset in enumerate(["wolf", "deer", "bear", "boar", "cat", "wolf"]):
        r = random.Random(100 + i)
        kp, (W, H) = keypoints_for(preset, r, ["left", "right"][i % 2])
        kp = jitter(kp, r)
        kp["ground_y"] = max(p["y"] for p in kp["front_leg"] + kp["hind_leg"])
        rep = fr.fit(kp, preset, W, H)
        glb = os.path.join(OUT, f"{preset}_noisy{i}.glb")
        muscle = round(r.uniform(0, 1), 2)
        built = build.main({"preset": preset, "muscle": muscle, "clear_scene": True,
                            "overrides": rep["overrides"], "export_path": glb})
        skinned = rig.main({"import_path": glb, "clear_scene": True})
        ok = built["non_manifold"] == 0 and skinned["unweighted_verts"] == 0
        print(f"[test] noisy fit {preset:5s} muscle {muscle:.2f}: non-manifold {built['non_manifold']}, "
              f"unweighted {skinned['unweighted_verts']}, warnings {len(rep['warnings'])} -> {'ok' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"noisy {preset}")

    # request/response path through a mock Gemini, plus the SVG overlay
    kp, (W, H) = keypoints_for("wolf", random.Random(3), "right")
    MockGemini.payload = kp
    png = os.path.join(OUT, "ref.png")
    import bpy
    img = bpy.data.images.new("ref", W, H)
    img.filepath_raw, img.file_format = png, "PNG"
    img.save()
    srv = HTTPServer(("127.0.0.1", 0), MockGemini)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ.update(GEMINI_API_KEY="test-key", GEMINI_API_BASE=f"http://127.0.0.1:{srv.server_port}")
    rep = fr.run(image=png, preset="wolf", out=os.path.join(OUT, "fit.json"), overlay=os.path.join(OUT, "fit.svg"))
    srv.shutdown()
    ok = rep["ok"] and rep["image_size"] == [W, H] and rep["source"].startswith("gemini") and os.path.exists(rep["overlay"])
    print(f"[test] fit via mock Gemini: size {rep['image_size']}, source {rep['source']} -> {'ok' if ok else 'FAIL'}")
    if not ok:
        failures.append("mock")

    print("[test] FIT FAILED: " + ", ".join(failures) if failures else "[test] FIT TESTS PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)

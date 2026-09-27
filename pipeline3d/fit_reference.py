# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
fit_reference.py - fit the low-poly creature builder to a side-view reference image.

    # 1. get a reference (Nano Banana, Gemini API key) and fit it in one go
    python fit_reference.py --generate "grey wolf" --image refs/wolf_side.png --preset wolf --out fit.json
    # 2. fit your own side-view photo or drawing
    python fit_reference.py --image my_horse.jpg --preset deer --animal horse --out fit.json --overlay fit.svg
    # 3. no key: hand-place the keypoints (same format Gemini returns, see --schema) and fit those
    python fit_reference.py --keypoints my_points.json --preset wolf --out fit.json

Gemini (vision, JSON output) marks the joints on the image: shoulder, elbow, wrist, fetlock and toe
of the near front leg; hip, stifle, hock, fetlock and toe of the near hind leg; torso depth at four
stations; neck, skull, muzzle, nose, ear tip and the tail. Those points become
build_lowpoly_creature.py overrides: spine and head joints with radii, tail, ear length, stance and
per-creature leg chains, so the legs bend where the reference's legs bend (a horse's long cannon
bones, a hyena's sloping back, a bear's flat feet) instead of following a generic stance.

What an image can't give is kept from the preset: body width (a side view has no depth), leg
spread and colours. Use it with images you generated or have the rights to.

Output (--out): {"ok", "preset", "overrides", "stance", "keypoints", "warnings", "image"}. Pass
"overrides" to build_lowpoly_creature.py, or let forge.py do it (generate.fit_reference).
Environment: GEMINI_API_KEY (or GOOGLE_API_KEY); GEMINI_API_BASE to point at a proxy or mock.
"""

import argparse
import base64
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BANANA = os.path.join(os.path.dirname(HERE), ".agents", "skills", "nano-banana", "scripts", "banana.py")
DEFAULT_MODEL = "gemini-3.5-flash"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

REFERENCE_PROMPT = (
    "Strict side view (lateral profile, orthographic, camera at shoulder height) of a {animal}, standing "
    "naturally with all four legs visible and separated: the near front leg slightly forward and the near "
    "hind leg slightly back, so the shoulder, elbow, wrist, hip, knee and hock of the near legs are each "
    "clearly visible. Whole animal in frame including ear tips, tail tip and hooves or paws; plain white "
    "background; even flat lighting; no cast shadow, no text, no props; realistic anatomy and natural "
    "adult proportions."
)

# Joint names, top to bottom, in the order build_lowpoly_creature.STANCES uses
FRONT_JOINTS = ["scapula_top", "shoulder", "elbow", "wrist", "fetlock_or_paw", "toe_tip"]
HIND_JOINTS = ["hip", "stifle_knee", "hock", "fetlock_or_paw", "toe_tip"]
STANCES = ("digitigrade", "unguligrade", "plantigrade")

# Presets' proportions that an image can't give, and their chest height (used as the fitted scale)
PRESET_BASICS = {
    "wolf": {"spread": 0.11, "chest_z": 0.68},
    "boar": {"spread": 0.13, "chest_z": 0.64},
    "bear": {"spread": 0.16, "chest_z": 0.82},
    "deer": {"spread": 0.10, "chest_z": 1.00},
    "cat": {"spread": 0.05, "chest_z": 0.29},
}

_PT = {"type": "OBJECT", "properties": {"x": {"type": "NUMBER"}, "y": {"type": "NUMBER"}},
       "required": ["x", "y"]}
_WPT = {"type": "OBJECT", "properties": {"x": {"type": "NUMBER"}, "y": {"type": "NUMBER"},
                                         "width": {"type": "NUMBER"}},
        "required": ["x", "y", "width"]}
_SLICE = {"type": "OBJECT", "properties": {"x": {"type": "NUMBER"}, "top": {"type": "NUMBER"},
                                           "bottom": {"type": "NUMBER"}},
          "required": ["x", "top", "bottom"]}
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_side_view": {"type": "BOOLEAN"},
        "facing": {"type": "STRING", "enum": ["left", "right"]},
        "stance": {"type": "STRING", "enum": list(STANCES)},
        "ground_y": {"type": "NUMBER"},
        "torso": {"type": "ARRAY", "items": _SLICE, "minItems": 4, "maxItems": 4},
        "neck": _SLICE, "skull": _SLICE, "muzzle": _SLICE,
        "nose": _PT, "ear_tip": _PT,
        "tail": {"type": "ARRAY", "items": _WPT, "minItems": 2, "maxItems": 5},
        "front_leg": {"type": "ARRAY", "items": _WPT, "minItems": 6, "maxItems": 6},
        "hind_leg": {"type": "ARRAY", "items": _WPT, "minItems": 5, "maxItems": 5},
    },
    "required": ["is_side_view", "facing", "stance", "ground_y", "torso", "neck", "skull", "muzzle",
                 "nose", "ear_tip", "tail", "front_leg", "hind_leg"],
}

DETECT_PROMPT = """You are measuring an animal for a 3D rig. The image shows a {animal} from the side.
Return image coordinates normalised to 0-1000 (x: 0 = left edge, 1000 = right edge; y: 0 = top, 1000 = bottom).
Measure the NEAR legs only (the ones closest to the camera, drawn on top), not the far legs.

- is_side_view: false if the animal is not seen roughly from the side.
- facing: which way the head points.
- stance: digitigrade (walks on toes: dog, cat, wolf), unguligrade (hooves: deer, horse, pig), plantigrade (whole foot: bear, human).
- ground_y: y of the ground line under the feet.
- torso: 4 vertical slices across the trunk, from the rump (tail end) to the chest (just behind the front leg):
  x of the slice, top = y of the back line, bottom = y of the belly/chest line at that x.
- neck: a slice at the middle of the neck (top and bottom edge of the neck, measured vertically).
- skull: a slice through the skull at the ears. muzzle: a slice at the middle of the muzzle/snout.
- nose: the tip of the nose. ear_tip: the tip of the near ear.
- tail: 2-5 points from the tail base to the tail tip along its centre line, width = tail thickness there.
- front_leg: exactly 6 points down the near front leg: {front}.
  Each point is the centre of the leg at that joint; width = leg thickness there (horizontal, same 0-1000 x units).
- hind_leg: exactly 5 points down the near hind leg: {hind}.
Anatomy check: the front elbow sits BEHIND the shoulder-wrist line; the hind knee (stifle) sits IN FRONT of the
hip-hock line and the hock points backward. Place the points where the joints really are, not on a straight line."""


# ----------------------------------------------------------------------------- image helpers

def image_size(path):
    """(width, height) of a PNG, JPEG or WebP, standard library only."""
    with open(path, "rb") as fh:
        head = fh.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            kind = head[12:16]
            if kind == b"VP8X":
                return 1 + int.from_bytes(head[24:27], "little"), 1 + int.from_bytes(head[27:30], "little")
            fh.seek(0)
            data = fh.read(40)
            if kind == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if kind == b"VP8L":
                b = data[21:25]
                return 1 + (((b[1] & 0x3F) << 8) | b[0]), 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            while True:
                marker = fh.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    break
                if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                    continue
                size = struct.unpack(">H", fh.read(2))[0]
                if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">xHH", fh.read(5))
                    return w, h
                fh.seek(size - 2, 1)
    raise ValueError(f"{path}: only PNG, JPEG and WebP images are supported")


def _mime(path):
    with open(path, "rb") as fh:
        head = fh.read(12)
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:2] == b"\xff\xd8":
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError(f"{path}: only PNG, JPEG and WebP images are supported")


def api_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


class NoKey(RuntimeError):
    pass


# ----------------------------------------------------------------------------- 1. reference image

def generate_reference(animal, out_path, model="nano-banana-2"):
    """Nano Banana side view through banana.py (Gemini API key, or Vertex AI credentials)."""
    if not (shutil.which("uv") and os.path.exists(BANANA)):
        raise RuntimeError("generating a reference needs uv and .agents/skills/nano-banana/scripts/banana.py")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    cmd = ["uv", "run", BANANA, "-p", REFERENCE_PROMPT.format(animal=animal), "-f", out_path,
           "-m", model, "-a", "3:2"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        err = (proc.stderr or proc.stdout).strip().splitlines()
        raise RuntimeError(f"Nano Banana failed: {err[-1] if err else 'unknown error'}")
    return out_path


# ----------------------------------------------------------------------------- 2. keypoints (Gemini)

def detect_keypoints(image_path, animal="animal", model=DEFAULT_MODEL, key=None, timeout=180):
    """Ask Gemini to mark the joints. Returns the keypoint dict (see SCHEMA)."""
    key = key or api_key()
    if not key:
        raise NoKey("set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey) or pass --keypoints")
    with open(image_path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    body = {
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": _mime(image_path), "data": data}},
            {"text": DETECT_PROMPT.format(animal=animal, front=", ".join(FRONT_JOINTS),
                                          hind=", ".join(HIND_JOINTS))},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    base = os.environ.get("GEMINI_API_BASE", API_BASE).rstrip("/")
    req = urllib.request.Request(f"{base}/models/{model}:generateContent", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Gemini {model} HTTP {exc.code}: {detail}") from None
    try:
        text = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
        return json.loads(text)
    except (KeyError, IndexError, ValueError):
        raise RuntimeError(f"Gemini returned no keypoints: {json.dumps(out)[:400]}") from None


# ----------------------------------------------------------------------------- 3. fit

def _check(kp):
    missing = [k for k in SCHEMA["required"] if k not in kp]
    if missing:
        raise ValueError(f"keypoints missing {missing}")
    if len(kp["front_leg"]) != 6 or len(kp["hind_leg"]) != 5 or len(kp["torso"]) != 4:
        raise ValueError("need exactly 6 front_leg, 5 hind_leg and 4 torso points")
    if kp.get("is_side_view") is False:
        raise ValueError("the image is not a side view; generate or pick a profile image")


def fit(kp, preset="wolf", width=1000, height=1000):
    """Keypoints (0-1000 image coords) -> build_lowpoly_creature overrides (metres, head at -Y)."""
    _check(kp)
    warnings = []
    basics = PRESET_BASICS.get(preset, PRESET_BASICS["wolf"])
    sx, sy = width / 1000.0, height / 1000.0          # back to pixels, so x and y share a unit
    sign = 1.0 if kp["facing"] == "right" else -1.0   # forward = toward the head
    xs = [t["x"] for t in kp["torso"]]
    xc = sum(xs) / len(xs) * sx
    ground = kp["ground_y"] * sy
    # the torso slices must run rump -> chest; flip if the model listed them head first
    if (kp["torso"][-1]["x"] - kp["torso"][0]["x"]) * sign < 0:
        kp = dict(kp, torso=list(reversed(kp["torso"])))
        warnings.append("torso slices were head-first; reversed")

    chest = kp["torso"][-1]
    chest_h = ground - (chest["top"] + chest["bottom"]) / 2 * sy
    if chest_h <= 0:
        raise ValueError("ground_y must be below the torso")
    s = basics["chest_z"] / chest_h                   # metres per pixel: chest height = preset's

    def world(x, y):          # image -> builder (y forward is -Y, z up)
        return -(x * sx - xc) * sign * s, (ground - y * sy) * s

    def slice_joint(sl, depth_frac=0.45):
        y, z = world(sl["x"], (sl["top"] + sl["bottom"]) / 2)
        r = abs(sl["bottom"] - sl["top"]) * sy * s * depth_frac
        return [round(y, 4), round(z, 4), round(max(r, 0.005), 4)]

    body = [slice_joint(t) for t in kp["torso"]]
    head = [slice_joint(kp["neck"]), slice_joint(kp["skull"]), slice_joint(kp["muzzle"], 0.40)]
    ny, nz = world(kp["nose"]["x"], kp["nose"]["y"])
    head.append([round(ny, 4), round(nz, 4), round(head[2][2] * 0.6, 4)])
    ey, ez = world(kp["ear_tip"]["x"], kp["ear_tip"]["y"])
    ears = max(0.0, ez - (head[1][1] + head[1][2]))   # ear tip above the top of the skull
    if ears < 0.01:
        warnings.append("ear tip is not above the skull; ears left short")

    # tail: steps from the rump joint, like the presets
    tail, prev = [], (body[0][0], body[0][1])
    for p in kp["tail"]:
        ty, tz = world(p["x"], p["y"])
        tail.append([round(ty - prev[0], 4), round(tz - prev[1], 4), round(max(p["width"] * sx * s / 2, 0.004), 4)])
        prev = (ty, tz)

    def leg(points, root_index):
        pts = [world(p["x"], p["y"]) + (p["width"] * sx * s / 2,) for p in points]
        y0 = pts[root_index][0]
        h = min(body, key=lambda j: abs(j[0] - y0))[1]          # the builder's spine_at(y0)
        return y0, h, pts

    fy0, fh, fpts = leg(kp["front_leg"], 1)
    hy0, hh, hpts = leg(kp["hind_leg"], 0)
    radii = [r for *_, r in fpts[2:] + hpts[2:]]
    leg_r = max(sorted(radii)[len(radii) // 2], 0.004)
    chains = {
        "front": [[round((fy0 - y) / fh, 4), round(max(z, 0.0) / fh, 4), round(min(max(r / leg_r, 0.3), 4.0), 3)]
                  for y, z, r in fpts],
        "hind": [[round((hy0 - y) / hh, 4), round(max(z, 0.0) / hh, 4), round(min(max(r / leg_r, 0.3), 4.0), 3)]
                 for y, z, r in hpts],
    }

    # anatomy sanity: elbow behind the shoulder-wrist line, stifle ahead of the hip-hock line
    def ahead(a, b, c):
        """How far b sits ahead (toward -Y, the head) of the line a-c, in metres."""
        t = (b[1] - a[1]) / ((c[1] - a[1]) or 1e-6)
        return (a[0] + (c[0] - a[0]) * t) - b[0]
    if ahead(fpts[1], fpts[2], fpts[3]) > 0.01:
        warnings.append("front elbow is ahead of the shoulder-wrist line (check the image: far leg picked?)")
    if ahead(hpts[0], hpts[1], hpts[2]) < -0.01:
        warnings.append("hind knee is behind the hip-hock line (check the image: far leg picked?)")
    for name, pts in (("front", fpts), ("hind", hpts)):
        if pts[0][1] < pts[-1][1]:
            raise ValueError(f"{name}_leg must run from the body down to the toe")

    overrides = {
        "stance": kp["stance"] if kp["stance"] in STANCES else "digitigrade",
        "body": body, "head": head, "ears": round(ears, 4), "tail": tail,
        "front_y": round(fy0, 4), "hind_y": round(hy0, 4),
        "leg_r": round(leg_r, 4), "spread": basics["spread"],
        "leg_chains": chains,
    }
    return {"ok": True, "preset": preset, "overrides": overrides, "stance": overrides["stance"],
            "scale_m_per_px": round(s, 6), "warnings": warnings}


# ----------------------------------------------------------------------------- overlay

def overlay_svg(image_path, kp, width, height, out_path):
    """The image with the detected joints drawn on it, to check the fit in a browser."""
    sx, sy = width / 1000.0, height / 1000.0
    P = lambda p: f"{p['x'] * sx:.1f},{p['y'] * sy:.1f}"
    with open(image_path, "rb") as fh:
        uri = f"data:{_mime(image_path)};base64,{base64.b64encode(fh.read()).decode()}"
    el = [f'<image href="{uri}" width="{width}" height="{height}"/>',
          f'<line x1="0" x2="{width}" y1="{kp["ground_y"] * sy:.1f}" y2="{kp["ground_y"] * sy:.1f}" stroke="#888" stroke-dasharray="8 6"/>']
    for sl in kp["torso"] + [kp["neck"], kp["skull"], kp["muzzle"]]:
        el.append(f'<line x1="{sl["x"] * sx:.1f}" x2="{sl["x"] * sx:.1f}" y1="{sl["top"] * sy:.1f}" '
                  f'y2="{sl["bottom"] * sy:.1f}" stroke="#2a9d8f" stroke-width="4"/>')
    for pts, colour in ((kp["front_leg"], "#e63946"), (kp["hind_leg"], "#1d70d6"), (kp["tail"], "#f4a261")):
        el.append(f'<polyline points="{" ".join(P(p) for p in pts)}" fill="none" stroke="{colour}" stroke-width="4"/>')
        el += [f'<circle cx="{p["x"] * sx:.1f}" cy="{p["y"] * sy:.1f}" r="{max(p["width"] * sx / 2, 4):.1f}" '
               f'fill="none" stroke="{colour}" stroke-width="2"/>' for p in pts]
    for p in (kp["nose"], kp["ear_tip"]):
        el.append(f'<circle cx="{p["x"] * sx:.1f}" cy="{p["y"] * sy:.1f}" r="6" fill="#2a9d8f"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
           f'height="{height}">{"".join(el)}</svg>')
    with open(out_path, "w") as fh:
        fh.write(svg)
    return out_path


# ----------------------------------------------------------------------------- driver

def run(image=None, preset="wolf", animal=None, keypoints=None, generate=None, model=DEFAULT_MODEL,
        banana_model="nano-banana-2", out=None, overlay=None):
    """Generate (optional) -> detect (or load keypoints) -> fit. Returns the fit report."""
    animal = animal or generate or preset
    if generate:
        if not image:
            raise ValueError("--generate needs --image (where to save the reference)")
        if not os.path.exists(image):
            generate_reference(generate, image, banana_model)
    if keypoints:
        with open(keypoints) as fh:
            kp = json.load(fh)
        source = "keypoints file"
    else:
        if not image or not os.path.exists(image):
            raise ValueError("need --image (a side view) or --keypoints")
        kp = detect_keypoints(image, animal, model)
        source = f"gemini {model}"
    # 0-1000 coordinates are per axis, so the fit needs the image's aspect: from the image, else
    # from the keypoints file ("image_size": [w, h]); square if neither
    w, h = image_size(image) if image and os.path.exists(image) else tuple(kp.get("image_size") or (1000, 1000))
    rep = fit(kp, preset, w, h)
    rep.update(keypoints=kp, image=image, image_size=[w, h], source=source)
    if overlay and image and os.path.exists(image):
        rep["overlay"] = overlay_svg(image, kp, w, h, overlay)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as fh:
            json.dump(rep, fh, indent=1)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", help="side-view reference (PNG/JPEG/WebP); with --generate, where to save it")
    ap.add_argument("--preset", default="wolf", choices=sorted(PRESET_BASICS))
    ap.add_argument("--animal", help="what the image shows (default: the --generate text or the preset)")
    ap.add_argument("--generate", metavar="ANIMAL", help="make the reference with Nano Banana first")
    ap.add_argument("--keypoints", help="use these keypoints instead of asking Gemini")
    ap.add_argument("--model", default=os.environ.get("FIT_MODEL", DEFAULT_MODEL), help="Gemini vision model")
    ap.add_argument("--banana-model", default="nano-banana-2")
    ap.add_argument("--out", help="write the fit report (JSON) here")
    ap.add_argument("--overlay", help="write an SVG of the image with the detected joints")
    ap.add_argument("--schema", action="store_true", help="print the keypoint format and exit")
    a = ap.parse_args(argv)
    if a.schema:
        print(json.dumps(SCHEMA, indent=1))
        return 0
    try:
        rep = run(a.image, a.preset, a.animal, a.keypoints, a.generate, a.model, a.banana_model, a.out, a.overlay)
    except (NoKey, RuntimeError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2 if isinstance(exc, NoKey) else 1
    print(json.dumps({k: rep[k] for k in ("ok", "preset", "stance", "warnings", "source")} |
                     {"out": a.out, "overlay": rep.get("overlay")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""gate2d.py - measures whether 2D game art is fit to ship, and says exactly what is wrong.

A "gate" is a check with a number and a limit. Art that passes every gate can go into the
game without a human squinting at it; art that fails tells you which re-roll or cleanup step
to do. Run it on the frames art_cleanup.py wrote (one PNG per frame, all the same size).

    python gate2d.py processed/hero --palette vase --target-height 64 --bg 2b2d3a
    python gate2d.py processed/hero --palette none --kind portrait --report hero_gate.json

The nine gates (limits are the defaults; every one has an option):
  alpha_fringe        share of edge pixels still tinted with the key colour     <= 2 %
  palette             share of solid pixels more than --palette-tolerance from
                      the nearest palette colour                                <= 1 %
  frame_size          every frame is the same size, no side over --max-dim (2048)
  feet_baseline       the lowest solid row moves at most 2 px (or 2 % of the frame
                      height) between frames, so the character does not bob     animations only
  silhouette_iou      overlap between consecutive frames' shapes (0 = unrelated,
                      1 = identical) stays >= 0.30, so no frame "pops"          animations only
  facing              no frame faces the other way than the frame before it
                      (catches AI sheets that flip the character)               --side-view only
  readability         shrunk to its on-screen height (--target-height), the figure
                      still has >= 120 solid pixels and >= 2.0 contrast against
                      the game's background colour (--bg)
  texture_budget      total PNG size <= --budget-kb (512) and <= 16 MB of video memory
  godot_import        Godot imports the files with zero warnings or errors
                      (needs --godot or the GODOT environment variable; skipped otherwise)

--kind picks which gates apply: sprite (all), tileset / portrait / background (no feet or IoU).
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

import numpy as np
from PIL import Image

# Lets "import art_cleanup" find the tool sitting next to this file.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import art_cleanup  # noqa: E402

# A pixel counts as part of the figure when its alpha is at least this (half visible).
SOLID_ALPHA = 128
# Which gates make sense for which kind of art.
ANIMATION_KINDS = {"sprite"}


def check(name: str, passed: bool | None, value, limit, detail: str = "") -> dict:
    """One gate result. passed=None means the gate was skipped (it does not count as a failure)."""
    return {"name": name, "passed": passed, "value": value, "limit": limit, "detail": detail}


def load_frames(source: pathlib.Path) -> tuple[list[pathlib.Path], list[np.ndarray]]:
    """Finds the frame PNGs and loads each as an (height, width, 4) RGBA array.

    `source` is a folder (every *_NN.png in it, or every .png if none are numbered; the
    *_strip.png overview is skipped) or a single image.
    """
    if source.is_file():
        paths = [source]
    else:
        pngs = sorted(p for p in source.glob("*.png") if not p.stem.endswith("_strip"))
        # stem[-2:] is the last two characters of the name without ".png", e.g. "03".
        numbered = [p for p in pngs if p.stem[-2:].isdigit()]
        paths = numbered or pngs
    return paths, [np.array(Image.open(p).convert("RGBA")) for p in paths]


def gate_alpha_fringe(frames: list[np.ndarray], key: tuple[int, int, int], limit: float) -> dict:
    """Edge pixels that still carry the key colour show as a coloured halo in the game.

    An edge pixel is a visible pixel with a fully transparent neighbour (up, down, left or
    right), or any half-transparent pixel. It is "fringe" when its key-ness is 40 or more.
    """
    edge_total = 0
    fringe_total = 0
    for rgba in frames:
        alpha = rgba[..., 3]
        visible = alpha > 0
        clear = ~visible
        # np.pad adds a transparent border so shifting never wraps around the image.
        padded = np.pad(clear, 1, constant_values=True)
        near_clear = padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]
        edge = visible & (near_clear | (alpha < 255))
        ness = art_cleanup.key_ness(rgba[..., :3].astype(np.int32), key)
        edge_total += int(edge.sum())
        fringe_total += int((edge & (ness >= 40)).sum())
    share = fringe_total / edge_total if edge_total else 0.0
    return check("alpha_fringe", share <= limit, round(share, 4), limit,
                 f"{fringe_total} of {edge_total} edge pixels tinted with the key colour")


def gate_palette(frames: list[np.ndarray], palette: np.ndarray | None, tolerance: float, limit: float) -> dict:
    """Solid pixels must sit on (or within `tolerance` of) a palette colour."""
    solid = np.concatenate([f[f[..., 3] >= SOLID_ALPHA][:, :3] for f in frames]).astype(np.int32)
    unique = len(np.unique(solid, axis=0)) if len(solid) else 0
    if palette is None:
        return check("palette", None, unique, None, f"no palette given; {unique} distinct colours")
    # Distance from every pixel to every palette colour, then keep the smallest per pixel.
    # solid[:, None, :] - palette[None, :, :] uses broadcasting: (pixels, 1, 3) - (1, colours, 3).
    nearest = np.sqrt(((solid[:, None, :] - palette[None, :, :]) ** 2).sum(axis=-1)).min(axis=1)
    share = float((nearest > tolerance).mean()) if len(solid) else 0.0
    return check("palette", share <= limit, round(share, 4), limit,
                 f"{unique} distinct colours, {len(palette)} in the palette, tolerance {tolerance}")


def gate_frame_size(frames: list[np.ndarray], max_dim: int) -> dict:
    """All frames the same size (so the sprite does not jump), and small enough for the web."""
    sizes = sorted({(f.shape[1], f.shape[0]) for f in frames})      # a set removes duplicates
    biggest = max(max(size) for size in sizes)
    ok = len(sizes) == 1 and biggest <= max_dim
    return check("frame_size", ok, [list(size) for size in sizes], f"one size, <= {max_dim} px",
                 f"{len(frames)} frame(s)")


def gate_feet_baseline(frames: list[np.ndarray], airborne: set[int], limit_px: float) -> dict:
    """The lowest solid row should be the same in every grounded frame."""
    bottoms = []
    for index, rgba in enumerate(frames):
        rows = np.flatnonzero((rgba[..., 3] >= SOLID_ALPHA).any(axis=1))
        if index not in airborne and len(rows):
            bottoms.append(int(rows[-1]))
    if len(bottoms) < 2:
        return check("feet_baseline", None, 0, limit_px, "fewer than two grounded frames")
    drift = max(bottoms) - min(bottoms)
    limit = max(limit_px, round(0.02 * frames[0].shape[0], 1))
    return check("feet_baseline", drift <= limit, drift, limit, f"lowest solid rows: {bottoms}")


def gate_silhouette_iou(frames: list[np.ndarray], minimum: float, loop: bool) -> dict:
    """Consecutive frames should overlap: a very low overlap reads as a pop or a different character.

    IoU = intersection over union = (pixels solid in BOTH frames) / (pixels solid in EITHER).
    Frames that are pixel-identical (IoU 1.0) are reported in the detail as wasted frames.
    """
    masks = [f[..., 3] >= SOLID_ALPHA for f in frames]
    if len(masks) < 2 or len({m.shape for m in masks}) != 1:
        return check("silhouette_iou", None, None, minimum, "needs two or more same-sized frames")
    pairs = list(zip(range(len(masks) - 1), range(1, len(masks))))
    if loop:
        pairs.append((len(masks) - 1, 0))           # the loop point: last frame back to the first
    ious = []
    for a, b in pairs:
        union = (masks[a] | masks[b]).sum()
        ious.append(float((masks[a] & masks[b]).sum() / union) if union else 1.0)
    worst = min(ious)
    duplicates = [f"{a}->{b}" for (a, b), iou in zip(pairs, ious) if iou >= 0.999]
    detail = f"min {worst:.2f} at frames {pairs[ious.index(worst)]}, mean {np.mean(ious):.2f}"
    if duplicates:
        detail += f"; identical frames: {', '.join(duplicates)}"
    return check("silhouette_iou", worst >= minimum, round(worst, 3), minimum, detail)


def gate_facing(frames: list[np.ndarray], side_view: bool, margin: float, loop: bool) -> dict:
    """In a side-view animation every frame must face the same way.

    AI sheets often flip the character between frames (walks left, then right, then left).
    The test: compare each frame with the next one twice, once as it is and once mirrored
    left-to-right. If the MIRRORED next frame fits clearly better (by `margin`), that frame
    faces the other way. Only meaningful for side views: a character seen from the front or
    back is symmetric, so this gate is skipped unless side_view is set.
    """
    masks = [f[..., 3] >= SOLID_ALPHA for f in frames]
    if not side_view or len(masks) < 2 or len({m.shape for m in masks}) != 1:
        return check("facing", None, None, margin, "side-view animations only (--side-view)")

    def iou(a: np.ndarray, b: np.ndarray) -> float:
        """Intersection over union of two solid-pixel masks."""
        union = (a | b).sum()
        return float((a & b).sum() / union) if union else 1.0

    pairs = list(zip(range(len(masks) - 1), range(1, len(masks))))
    if loop:
        pairs.append((len(masks) - 1, 0))
    # m[:, ::-1] reverses the columns of the mask: a left-right mirror image.
    flips = [(a, b) for a, b in pairs if iou(masks[a], masks[b][:, ::-1]) - iou(masks[a], masks[b]) > margin]
    return check("facing", not flips, len(flips), 0,
                 "frames facing the other way than the one before: " + (", ".join(f"{a}->{b}" for a, b in flips) or "none"))


# Shared by the readability gate: how bright a colour looks to the eye.
def luminance(rgb: np.ndarray) -> np.ndarray:
    """Relative luminance (0 = black, 1 = white) by the WCAG accessibility formula."""
    c = rgb.astype(np.float64) / 255.0
    linear = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]


# Gate 6: can you still see the figure at the size the player sees it?
def gate_readability(frames: list[np.ndarray], target_height: int, bg: tuple[int, int, int],
                     min_pixels: int, min_contrast: float) -> dict:
    """Shrinks the art to its on-screen size and asks: is there still a figure to see?

    Two numbers: how many solid pixels the smallest frame keeps, and the median contrast of
    those pixels against the game's background (WCAG contrast ratio: 1 = same colour, 21 =
    black on white). A character that melts into the level fails here.
    """
    tallest = 1
    for rgba in frames:
        rows = np.flatnonzero((rgba[..., 3] >= SOLID_ALPHA).any(axis=1))
        if len(rows):
            tallest = max(tallest, int(rows[-1] - rows[0] + 1))
    scale = min(1.0, target_height / tallest)       # never enlarge: that would hide problems
    bg_lum = float(luminance(np.array(bg)))
    fewest = None
    contrasts = []
    for rgba in frames:
        size = (max(1, round(rgba.shape[1] * scale)), max(1, round(rgba.shape[0] * scale)))
        small = np.array(art_cleanup.resize_rgba(Image.fromarray(rgba), size))
        solid = small[..., 3] >= SOLID_ALPHA
        count = int(solid.sum())
        fewest = count if fewest is None else min(fewest, count)
        if count:
            lum = luminance(small[solid][:, :3])
            lighter, darker = np.maximum(lum, bg_lum), np.minimum(lum, bg_lum)
            contrasts.append(float(np.median((lighter + 0.05) / (darker + 0.05))))
    contrast = min(contrasts) if contrasts else 0.0
    ok = (fewest or 0) >= min_pixels and contrast >= min_contrast
    return check("readability", ok, {"solid_pixels": fewest, "contrast": round(contrast, 2)},
                 {"solid_pixels": min_pixels, "contrast": min_contrast},
                 f"figure {tallest} px tall shown at {round(tallest * scale)} px on #{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}")


def gate_texture_budget(paths: list[pathlib.Path], frames: list[np.ndarray], budget_kb: float, vram_mb: float) -> dict:
    """Download size (PNG bytes) and video memory (width x height x 4 bytes, uncompressed)."""
    kb = sum(p.stat().st_size for p in paths) / 1024.0
    vram = sum(f.shape[0] * f.shape[1] * 4 for f in frames) / (1024.0 * 1024.0)
    return check("texture_budget", kb <= budget_kb and vram <= vram_mb,
                 {"png_kb": round(kb, 1), "vram_mb": round(vram, 2)},
                 {"png_kb": budget_kb, "vram_mb": vram_mb}, f"{len(paths)} file(s)")


def gate_godot_import(paths: list[pathlib.Path], godot: str | None) -> dict:
    """Copies the files into a throwaway Godot project and imports them headless.

    Any line with WARNING or ERROR fails the gate; so does a file Godot did not import.
    """
    if godot == "off":
        return check("godot_import", None, None, 0, "skipped: --godot off")
    godot = godot or os.environ.get("GODOT")
    if not godot or not (shutil.which(godot) or pathlib.Path(godot).is_file()):
        return check("godot_import", None, None, 0, "skipped: pass --godot or set GODOT to the console exe")
    # "with" creates the temp folder and deletes it afterwards, even if something fails.
    with tempfile.TemporaryDirectory() as folder:
        project = pathlib.Path(folder)
        (project / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="gate"\n'
            'config/features=PackedStringArray("4.7", "GL Compatibility")\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        for p in paths:
            shutil.copy(p, project / p.name)
        try:
            run = subprocess.run([godot, "--headless", "--path", str(project), "--import"],
                                 capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return check("godot_import", False, "timeout", 0, "Godot did not finish importing in 180 s")
        lines = (run.stdout + run.stderr).splitlines()
        problems = [line.strip() for line in lines if "WARNING" in line or "ERROR" in line]
        missing = [p.name for p in paths if not (project / (p.name + ".import")).exists()]
    ok = not problems and not missing and run.returncode == 0
    detail = "; ".join(problems[:3]) if problems else (f"not imported: {missing}" if missing else "clean import")
    return check("godot_import", ok, len(problems) + len(missing), 0, detail)


# The entry point other scripts import: run_gate(folder, kind=..., palette=...) -> report dict.
def run_gate(source: pathlib.Path, *, kind: str = "sprite", palette: str = "none", key_color: str = "magenta",
             target_height: int = 64, bg: str = "808080", budget_kb: float = 512.0, vram_mb: float = 16.0,
             max_dim: int = 2048, palette_tolerance: float = 10.0, palette_limit: float = 0.01,
             fringe_limit: float = 0.02, baseline_px: float = 2.0, iou_min: float = 0.30, loop: bool = False,
             airborne: tuple[int, ...] = (), min_pixels: int = 120, min_contrast: float = 2.0,
             side_view: bool = False, facing_margin: float = 0.2, godot: str | None = None) -> dict:
    """Runs every gate that applies to `kind` and returns the report dictionary.

    The "*" in the signature makes every option keyword-only: callers must write
    run_gate(path, kind="portrait"), which keeps long calls readable.
    """
    started = time.perf_counter()
    paths, frames = load_frames(source)
    if not frames:
        raise ValueError(f"no PNG frames found in {source}")
    animated = kind in ANIMATION_KINDS
    checks = [
        gate_alpha_fringe(frames, art_cleanup.load_key_colour(key_color), fringe_limit),
        gate_palette(frames, art_cleanup.load_palette(palette), palette_tolerance, palette_limit),
        gate_frame_size(frames, max_dim),
    ]
    if animated:
        checks.append(gate_feet_baseline(frames, set(airborne), baseline_px))
        checks.append(gate_silhouette_iou(frames, iou_min, loop))
        checks.append(gate_facing(frames, side_view, facing_margin, loop))
    if kind == "background":
        # A wall or backdrop IS what figures are read against, so the gate has nothing to compare.
        checks.append(check("readability", None, None, None, "skipped: backgrounds are what art is read against"))
    else:
        checks.append(gate_readability(frames, target_height, art_cleanup.parse_hex(bg), min_pixels, min_contrast))
    checks.append(gate_texture_budget(paths, frames, budget_kb, vram_mb))
    checks.append(gate_godot_import(paths, godot))
    failed = [c["name"] for c in checks if c["passed"] is False]
    return {
        "asset": source.name, "kind": kind, "frames": len(frames),
        "passed": not failed, "failed": failed,
        "skipped": [c["name"] for c in checks if c["passed"] is None],
        "checks": checks, "gate_seconds": round(time.perf_counter() - started, 2),
    }


def build_parser() -> argparse.ArgumentParser:
    """Command-line options (argparse writes --help from these)."""
    parser = argparse.ArgumentParser(description="Gate 2D game art: measure it against shipping limits.")
    parser.add_argument("source", type=pathlib.Path, help="folder of frame PNGs, or one PNG")
    parser.add_argument("--kind", default="sprite", choices=["sprite", "tileset", "portrait", "background"])
    parser.add_argument("--palette", default="none", help="vase | none | hex list | .hex/.gpl file (default none)")
    parser.add_argument("--key-color", default="magenta", help="the background colour that was keyed out")
    parser.add_argument("--target-height", type=int, default=64, help="figure height on screen, px")
    parser.add_argument("--bg", default="808080", help="the game's background colour behind this art (hex)")
    parser.add_argument("--budget-kb", type=float, default=512.0, help="max total PNG size")
    parser.add_argument("--max-dim", type=int, default=2048, help="max width or height of a frame")
    parser.add_argument("--iou-min", type=float, default=0.30, help="lowest allowed overlap between frames")
    parser.add_argument("--loop", action="store_true", help="also compare the last frame with the first")
    parser.add_argument("--side-view", action="store_true",
                        help="side-view animation: also check that no frame is flipped left-right")
    parser.add_argument("--airborne", default="", help="frame numbers exempt from the feet gate, e.g. 6,7")
    parser.add_argument("--godot", default=None, help="Godot console exe for the import gate (or set GODOT); 'off' skips it")
    parser.add_argument("--report", type=pathlib.Path, default=None, help="write the JSON report here")
    return parser


def main(argv: list[str] | None = None) -> dict:
    """Parses options, runs the gates, prints a one-line verdict per gate, writes the report."""
    args = build_parser().parse_args(argv)
    airborne = tuple(int(n) for n in args.airborne.split(",") if n.strip())
    report = run_gate(args.source, kind=args.kind, palette=args.palette, key_color=args.key_color,
                      target_height=args.target_height, bg=args.bg, budget_kb=args.budget_kb,
                      max_dim=args.max_dim, iou_min=args.iou_min, loop=args.loop, airborne=airborne, side_view=args.side_view,
                      godot=args.godot)
    for c in report["checks"]:
        verdict = "skip" if c["passed"] is None else ("PASS" if c["passed"] else "FAIL")
        print(f"  {verdict}  {c['name']:<15} {c['value']}  (limit {c['limit']})  {c['detail']}")
    print(f"{'PASSED' if report['passed'] else 'FAILED: ' + ', '.join(report['failed'])}"
          f"  {report['asset']}  ({report['gate_seconds']} s)")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    sys.exit(0 if main()["passed"] else 1)

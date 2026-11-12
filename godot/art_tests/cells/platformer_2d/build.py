"""platformer_2d/build.py - platformer cell, 2D art: a flat-silhouette puppet and a flat backdrop.

The cheap proven style: flat silhouettes (think paper-cut or shadow-play platformers).
Flat single-colour shapes hide every joint, so a four-part puppet (head, body, arm, leg) looks
finished, and its run cycle is a sine wave on the joint angles: no drawn frames at all.
Platforms are flat coloured rectangles made in code, so the only environment art is a backdrop.

    python build.py            # re-runs are free: images are cached in raw/

Pipeline: 2 Nano Banana images -> parts sliced by position -> rig.json -> gate2d -> demo.tscn
(the shared cut_out_puppet.gd) -> screenshot.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, art_cleanup, gate2d  # noqa: E402

PARTS = ("head", "body", "arm", "leg")          # left-to-right order asked for in the prompt
PARTS_PROMPT = (
    "Cut-out puppet parts sheet for a flat-silhouette 2D platformer character, paper-cut style. "
    "The character is a small fox-eared explorer shown in side view facing right. Every part is "
    "one flat solid deep-navy shape with NO outline, NO shading, NO gradients and NO texture; "
    "the only other colour is a bright orange scarf on the body and a small white dot for the eye. "
    "Show exactly four separate parts in ONE horizontal row with wide gaps, never touching, in "
    "this exact order from left to right: 1) the head with two pointed ears, 2) the body (a "
    "rounded torso with the orange scarf, no arms, no legs, no head), 3) one arm with a mitten "
    "hand, 4) one leg with a boot. The arm and the leg are drawn straight and vertical, hanging "
    "down, with rounded tops. All parts at the same scale. Background is one flat solid pure "
    "magenta colour (#FF00FF). No text, no labels, no guide lines."
)
BACKDROP_PROMPT = (
    "Flat paper-cut style background for a 2D platformer, side view: layered silhouettes of rolling "
    "hills and tall pine trees in four flat tones from pale peach near the sky to dusty rose and "
    "muted plum at the front, a large pale sun low on the horizon, flat solid colours only, no "
    "outlines, no gradients, no texture. Light and calm so a dark character stands out. "
    "No characters, no animals, no text."
)
FIGURE_PX = 120          # height of the assembled explorer on a 720p screen


def slice_parts(raw: pathlib.Path, out_dir: pathlib.Path) -> dict:
    """Keys the sheet and writes each part as its own tightly cropped picture at one scale.

    Same method as fighter_2d: blobs are read left to right and named by position.
    Returns {part name: [width, height]} in output pixels.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    key = art_cleanup.load_key_colour("magenta")
    rgba = art_cleanup.key_out(np.array(Image.open(raw).convert("RGBA")), key, 40)
    masks = art_cleanup.sort_reading_order(art_cleanup.find_frames(rgba[..., 3], gap=6, min_area=1500))
    if len(masks) != len(PARTS):
        raise ValueError(f"expected {len(PARTS)} parts, the slicer found {len(masks)}")
    boxes = [art_cleanup.bbox(mask) for mask in masks]
    heights = {name: box[3] - box[1] for name, box in zip(PARTS, boxes)}
    # Standing height is roughly head + body + leg, minus the overlaps at neck and hip.
    scale = FIGURE_PX / ((heights["head"] + heights["body"] + heights["leg"]) * 0.85)
    sizes = {}
    for name, mask, (left, top, right, bottom) in zip(PARTS, masks, boxes):
        crop = rgba[top:bottom, left:right].copy()
        crop[~mask[top:bottom, left:right], 3] = 0
        size = (round((right - left) * scale), round((bottom - top) * scale))
        part = art_cleanup.despill(np.array(art_cleanup.resize_rgba(Image.fromarray(crop), size)), key)
        Image.fromarray(part).save(out_dir / f"{name}.png")
        sizes[name] = list(size)
    return sizes


def write_rig(sizes: dict, path: pathlib.Path) -> None:
    """Writes rig.json for cut_out_puppet.gd (see that file for what each field means)."""
    rig = {
        "body": {"parent": "", "pivot": [0.5, 0.9], "attach": [0.0, 0.0]},
        "head": {"parent": "body", "pivot": [0.45, 0.88], "attach": [0.5, 0.12]},
        "arm": {"back": True, "parent": "body", "pivot": [0.5, 0.1], "attach": [0.5, 0.3]},
        "leg": {"back": True, "parent": "body", "pivot": [0.5, 0.08], "attach": [0.5, 0.88]},
    }
    # Limbs came out long for the round body; two correction factors, tuned by eye once.
    scales = {"body": 1.0, "head": 1.0, "arm": 0.7, "leg": 0.72}
    for name, entry in rig.items():
        entry["size"] = sizes[name]
        entry["scale"] = scales[name]
    path.write_text(json.dumps(rig, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("platformer_2d", "nano-banana flat parts sheet -> puppet with procedural run", CELL) as log:
        parts_raw = cell_lib.generate(log, CELL, "explorer_parts", PARTS_PROMPT, aspect="16:9")
        backdrop_raw = cell_lib.generate(log, CELL, "backdrop", BACKDROP_PROMPT, aspect="16:9")
        if "--generate-only" in sys.argv:
            return
        assets = CELL / "assets"
        with log.step("slice parts"):
            sizes = slice_parts(parts_raw, assets / "explorer")
            write_rig(sizes, assets / "explorer" / "rig.json")
        cell_lib.looked(log, "parts sheet: four flat parts in the right order")
        log.add_step("tune two limb scales by eye", 120.0, human=True)
        cell_lib.cleanup(log, backdrop_raw, assets / "backdrop", "backdrop", "--single", "--no-snap", "--size", "1280x720")
        cell_lib.looked(log, "backdrop: flat, pale, nothing that reads as a platform")
        # The explorer is seen against the backdrop: use its average colour for readability.
        backdrop = Image.open(assets / "backdrop" / "backdrop_00.png").convert("RGB").resize((64, 36))
        red, green, blue = (sum(channel) // len(channel) for channel in zip(*backdrop.getdata()))
        with log.step("gates"):
            for name in PARTS:
                log.add_gate(gate2d.run_gate(assets / "explorer" / f"{name}.png", kind="portrait",
                                             target_height=sizes[name][1], bg=f"{red:02x}{green:02x}{blue:02x}",
                                             min_pixels=60, godot="off"))
            log.add_gate(gate2d.run_gate(assets / "backdrop" / "backdrop_00.png", kind="background",
                                         budget_kb=1500, godot="off"))
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

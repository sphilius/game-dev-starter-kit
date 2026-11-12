"""fighter_2d/build.py - fighter cell, 2D art: a cut-out puppet from ONE image.

The cheap proven style: cut-out ("paper doll") animation. Instead of drawing every frame of
every punch, the character is drawn once as separate body parts. The parts are pinned
together at the joints with bones (Skeleton2D), and every pose is just a set of angles.
A fighter needs dozens of frames per move; a puppet needs zero new art per move.

    python build.py            # re-runs are free: images are cached in raw/

Pipeline: 2 Nano Banana images -> parts sliced and named by position -> rig.json (pivots)
-> gate2d -> demo.tscn (Skeleton2D mirror match) -> screenshot.
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

# The order of the parts in the prompt IS the rig: the slicer reads blobs left to right, so
# the first blob is the head, the second the torso, and so on. No hand labelling.
PARTS = ("head", "torso", "upper_arm", "forearm", "thigh", "shin")
PARTS_PROMPT = (
    "Cut-out animation puppet parts sheet for a 2D fighting game character, clean HD cartoon "
    "style with bold outlines and flat cel shading. The character is a muscular female boxer "
    "with a short dark ponytail, teal sports top, black shorts, red boxing gloves and white "
    "boots, drawn in side view facing right. "
    "Show exactly six separate body parts in ONE horizontal row with wide gaps between them, "
    "never touching or overlapping, in this exact order from left to right: "
    "1) the head with neck, 2) the torso from shoulders to hips with no arms and no legs, "
    "3) one upper arm, 4) one forearm with the boxing glove, 5) one thigh, "
    "6) one lower leg with the boot. "
    "Every arm and leg part is drawn straight and vertical, hanging down, with rounded ends "
    "so the parts can overlap at the joints. All parts are drawn at the same scale, as if the "
    "assembled character were taken apart. Background is one flat solid pure magenta colour "
    "(#FF00FF). No text, no labels, no numbers, no guide lines."
)
STAGE_PROMPT = (
    "Background for a 2D fighting game stage, side view: a rooftop boxing ring area at dusk with "
    "a glowing city skyline behind, string lights overhead, clean HD cartoon style with flat cel "
    "shading, muted colours so fighters stand out. The ground is a flat empty floor filling the "
    "bottom fifth of the picture. No characters, no people, no text, no logos."
)
FIGURE_PX = 330          # height of the assembled fighter on a 720p screen


def slice_parts(raw: pathlib.Path, out_dir: pathlib.Path) -> dict:
    """Keys the sheet, cuts out each part tightly and writes them with a shared scale.

    Unlike a sprite sheet, puppet parts must NOT be feet-aligned or padded to one cell size:
    each part keeps its own tight rectangle so its joint can be found from its corners.
    Returns {part name: [width, height]} in output pixels.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    key = art_cleanup.load_key_colour("magenta")
    rgba = art_cleanup.key_out(np.array(Image.open(raw).convert("RGBA")), key, 40)
    masks = art_cleanup.sort_reading_order(art_cleanup.find_frames(rgba[..., 3], gap=6, min_area=1500))
    if len(masks) != len(PARTS):
        raise ValueError(f"expected {len(PARTS)} parts, the slicer found {len(masks)}")
    boxes = [art_cleanup.bbox(mask) for mask in masks]
    # One scale for everything. A standing figure is about head + torso + thigh + shin tall
    # (minus overlaps), so scale that sum to the target height.
    heights = {name: box[3] - box[1] for name, box in zip(PARTS, boxes)}
    stack = heights["head"] + heights["torso"] + heights["thigh"] + heights["shin"]
    scale = FIGURE_PX / (stack * 0.9)
    sizes = {}
    for name, mask, (left, top, right, bottom) in zip(PARTS, masks, boxes):
        crop = rgba[top:bottom, left:right].copy()
        crop[~mask[top:bottom, left:right], 3] = 0            # "~" flips True/False: clear other parts
        size = (round((right - left) * scale), round((bottom - top) * scale))
        part = art_cleanup.despill(np.array(art_cleanup.resize_rgba(Image.fromarray(crop), size)), key)
        Image.fromarray(part).save(out_dir / f"{name}.png")
        sizes[name] = list(size)
    return sizes


def write_rig(sizes: dict, path: pathlib.Path) -> None:
    """Writes rig.json: where each part pivots, and where it attaches to its parent.

    No measuring by hand. Because the prompt asked for limbs drawn vertical, every limb's
    joint is "top centre, a little way in". Attachment points are fractions of the PARENT
    part's size (0,0 = its top-left corner, 1,1 = its bottom-right).
    """
    rig = {
        # part: parent, pivot (fraction of own size), attach (fraction of parent size).
        # "back": True also makes a darker far-side copy (the other arm, the other leg).
        "torso": {"parent": "", "pivot": [0.5, 0.95], "attach": [0.0, 0.0]},
        "head": {"parent": "torso", "pivot": [0.45, 0.92], "attach": [0.5, 0.1]},
        "upper_arm": {"back": True, "parent": "torso", "pivot": [0.5, 0.12], "attach": [0.5, 0.2]},
        "forearm": {"back": True, "parent": "upper_arm", "pivot": [0.5, 0.08], "attach": [0.5, 0.9]},
        "thigh": {"back": True, "parent": "torso", "pivot": [0.5, 0.1], "attach": [0.5, 0.9]},
        "shin": {"back": True, "parent": "thigh", "pivot": [0.5, 0.06], "attach": [0.5, 0.92]},
    }
    # The AI drew the parts at slightly different scales (long thin arms, small torso), so each
    # part gets a correction factor. These six numbers were tuned by eye against the screenshot:
    # the one manual step of this pipeline (about five minutes, logged as human time).
    scales = {"torso": 1.35, "head": 1.1, "upper_arm": 0.8, "forearm": 0.8, "thigh": 1.1, "shin": 0.9}
    for name, entry in rig.items():
        entry["size"] = sizes[name]
        entry["scale"] = scales[name]
    path.write_text(json.dumps(rig, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("fighter_2d", "nano-banana parts sheet -> Skeleton2D puppet", CELL) as log:
        parts_raw = cell_lib.generate(log, CELL, "boxer_parts", PARTS_PROMPT, aspect="16:9")
        stage_raw = cell_lib.generate(log, CELL, "stage", STAGE_PROMPT, aspect="16:9")
        if "--generate-only" in sys.argv:
            return
        assets = CELL / "assets"
        with log.step("slice parts"):
            sizes = slice_parts(parts_raw, assets / "boxer")
            write_rig(sizes, assets / "boxer" / "rig.json")
        cell_lib.looked(log, "parts sheet: six parts, right order, limbs vertical")
        log.add_step("tune six part scales by eye", 300.0, human=True)
        log.fail_mode("parts on one sheet are not drawn at one scale: arms came out long, torso small")
        cell_lib.cleanup(log, stage_raw, assets / "stage", "stage", "--single", "--no-snap", "--size", "1280x720")
        cell_lib.looked(log, "stage: empty floor, nothing that looks like a character")
        with log.step("gates"):
            # Parts are separate pictures of different sizes, so they are gated one by one as
            # stills ("portrait" kind = no animation gates). A lone thigh cannot be "readable",
            # so the contrast limit is off here; the assembled fighter is judged in the screenshot.
            for name in PARTS:
                log.add_gate(gate2d.run_gate(assets / "boxer" / f"{name}.png", kind="portrait",
                                             target_height=sizes[name][1], bg="4a4660", min_pixels=60, min_contrast=0.0, godot="off"))
            log.add_gate(gate2d.run_gate(assets / "stage" / "stage_00.png", kind="background", budget_kb=1500, godot="off"))
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

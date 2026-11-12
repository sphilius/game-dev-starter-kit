"""action_rpg_2d/build.py - action RPG cell, 2D art: a top-down walk sheet and a ground tile.

The cheap proven style: 16-bit top-down ("overhead") sprites. The risky part of this style is
the four-direction walk: 16 frames that must all be the same character. This cell asks for all
16 in ONE image (one request, one consistent character) instead of 16 requests.

    python build.py            # re-runs are free: images are cached in raw/

Pipeline: 2 Nano Banana images -> art_cleanup -> gate2d per direction -> demo.tscn -> screenshot.
"""
import pathlib
import shutil
import sys

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
from PIL import Image, ImageOps  # noqa: E402

import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

HERO_PROMPT = (
    "Sprite sheet for a top-down action RPG hero in the style of classic 16-bit overhead adventure "
    "games, seen from a high three-quarter overhead angle. One character: a young ranger with a "
    "bright green hooded cloak, tan tunic, brown boots and a short sword on the back. "
    "A strict grid of 4 rows and 4 columns, 16 frames, evenly spaced, frames not touching each "
    "other, every frame the same size and the same character. "
    "Row 1: walk cycle facing the viewer (walking down). Row 2: walk cycle facing left. "
    "Row 3: walk cycle facing right. Row 4: walk cycle facing away (walking up). "
    "Each row is a 4-frame walk: contact, passing, contact with the other leg, passing. "
    "Clean readable pixel art, dark outline, bright colours. Background is one flat solid pure "
    "magenta colour (#FF00FF), no ground, no shadows, no text, no labels, no grid lines."
)
GROUND_PROMPT = (
    "Seamless tileable square ground texture for a top-down 16-bit RPG: short green grass seen "
    "from directly above with a few tiny flowers and pebbles scattered evenly, pixel art, evenly "
    "lit, no shadows, nothing larger than a pebble, the left edge matches the right edge and the "
    "top edge matches the bottom edge. No text."
)
# Take 2: one request per direction, each with take 1 as the reference image so the character
# stays the same. {facing} is filled in by str.format() below. Left is not generated at all:
# it is the right-facing row mirrored, which is free and guaranteed to match.
ROW_PROMPT = (
    "Using the character in the reference image (same ranger, same colours, same pixel-art style, "
    "same overhead camera angle), draw a new sprite sheet with exactly four frames in one "
    "horizontal row, evenly spaced, not touching, all the same size, feet on the same line. "
    "It is a 4-frame walk cycle with the character {facing} in EVERY frame: "
    "1) left foot forward, 2) feet together, 3) right foot forward, 4) feet together. "
    "The legs and arms must clearly differ between frames. Background is one flat solid pure "
    "magenta colour (#FF00FF), no ground, no shadows, no text."
)
FACINGS = {
    "down": "facing the viewer, walking toward the camera",
    "right": "in side view facing RIGHT, walking to the right",
    "up": "seen from behind, walking away from the camera",
}
# Ground take 2: a PALE ground. Measured first with gate2d --bg on five candidate colours;
# only pale sand passed in every direction (contrast 2.6 to 3.8).
SAND_PROMPT = (
    "Seamless tileable square ground texture for a top-down 16-bit RPG: pale sandy dry earth seen "
    "from directly above, light tan colour, with a few tiny pebbles and sparse dry grass tufts "
    "scattered evenly, pixel art, evenly lit, no shadows, nothing larger than a pebble, the left "
    "edge matches the right edge and the top edge matches the bottom edge. No text."
)
DIRECTIONS = ("down", "left", "right", "up")


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("action_rpg_2d", "nano-banana 4x4 walk sheet + ground tile", CELL) as log:
        hero_raw = cell_lib.generate(log, CELL, "ranger", HERO_PROMPT, aspect="1:1")
        ground_raw = cell_lib.generate(log, CELL, "grass", GROUND_PROMPT, aspect="1:1")
        if "--generate-only" in sys.argv:
            return
        assets = CELL / "assets"
        # Take 1 (the 4x4 grid) kept the character consistent but got the directions wrong: the
        # side rows alternate left and right, and the facing-down row barely moves. The new
        # facing gate reports this (4 flips in a 4-frame row), so no human had to spot it.
        cell_lib.cleanup(log, hero_raw, cell_lib.ART_TESTS / "runs" / "action_rpg_2d_grid", "grid", "--fit-height", "64", "--palette", "none")
        side_row = cell_lib.ART_TESTS / "runs" / "action_rpg_2d_grid" / "row_side"
        side_row.mkdir(parents=True, exist_ok=True)
        for column in range(4):
            shutil.copy(cell_lib.ART_TESTS / "runs" / "action_rpg_2d_grid" / f"grid_{4 + column:02d}.png", side_row / f"side_{column}.png")
        rejected = gate2d.run_gate(side_row, kind="sprite", side_view=True, loop=True, godot="off")
        log.reroll(f"4x4 grid sheet: side row flips direction {rejected['checks'][5]['value']} times in 4 frames")
        log.fail_mode("one image with all four directions: character stays on-model, directions do not")
        for direction, facing in FACINGS.items():        # .items() gives (key, value) pairs
            row_raw = cell_lib.generate(log, CELL, f"ranger_{direction}", ROW_PROMPT.format(facing=facing),
                                        aspect="16:9", refs=(hero_raw,))
            # --scale would be better than --fit-height if the rows differ in size; the gate
            # result below shows whether they do.
            cell_lib.cleanup(log, row_raw, assets / "ranger" / direction, direction,
                             "--fit-height", "64", "--palette", "none")
        cell_lib.looked(log, "three direction rows: same ranger, walking, facing the right way")
        # Left = right mirrored. ImageOps.mirror flips a picture left to right.
        (assets / "ranger" / "left").mkdir(exist_ok=True)
        for frame in sorted((assets / "ranger" / "right").glob("right_0?.png")):
            ImageOps.mirror(Image.open(frame)).save(assets / "ranger" / "left" / frame.name.replace("right", "left"))
        # Green ranger on green grass: contrast 1.62 against a limit of 2.0, and darkening the
        # grass did not help (the dark boots then vanish instead). A pale ground does.
        log.reroll("ground: green hero on green grass, readability 1.62")
        log.fail_mode("hero and ground generated separately came out the same green (contrast 1.62)")
        log.add_step("review: rejected grass", cell_lib.GLANCE_SECONDS, human=True)
        ground_raw = cell_lib.generate(log, CELL, "sand", SAND_PROMPT, aspect="1:1")
        cell_lib.cleanup(log, ground_raw, assets / "ground", "ground", "--single", "--no-snap", "--size", "64x64")
        cell_lib.looked(log, "ground tile: no obvious seam when repeated")
        tile = Image.open(assets / "ground" / "ground_00.png").convert("RGB")
        # getdata() lists every pixel; zip(*...) regroups them into the R, G and B columns.
        red, green, blue = (sum(channel) // len(channel) for channel in zip(*tile.getdata()))
        ground_bg = f"{red:02x}{green:02x}{blue:02x}"      # the real average colour behind the hero
        with log.step("gates"):
            # One gate run per direction: the overlap gate only means something inside ONE
            # animation (see gates/README.md). The side rows also get the facing gate.
            for direction in DIRECTIONS:
                report = gate2d.run_gate(assets / "ranger" / direction, kind="sprite", target_height=64, bg=ground_bg,
                                         loop=True, side_view=direction in ("left", "right"), godot="off")
                # {**a, "k": v} copies the report and replaces one entry (the asset name).
                log.add_gate({**report, "asset": f"ranger_{direction}"})
            log.add_gate(gate2d.run_gate(assets / "ground" / "ground_00.png", kind="background", godot="off"))
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

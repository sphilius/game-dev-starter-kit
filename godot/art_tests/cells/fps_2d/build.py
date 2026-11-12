"""fps_2d/build.py - FPS cell, 2D art: billboard enemy sprites and a wall texture in a 3D level.

The cheap proven style: "boomer shooter". Enemies are flat pictures that always face the
camera (billboards), walls are small repeating textures, fog hides everything far away.
One image holds every enemy pose, so the character stays on-model without frame-by-frame work.

    GODOT=<console exe> python build.py        # re-runs are free: images are cached in raw/

Pipeline: 2 Nano Banana images -> art_cleanup -> gate2d -> demo.tscn -> screenshot.png.
"""
import pathlib
import sys

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

# One sheet, four poses, flat magenta behind them so the background can be removed exactly.
ENEMY_PROMPT = (
    "Sprite sheet for a retro first-person shooter enemy, in the style of 1990s pixel-art shooters. "
    "One character: a gaunt hooded cultist in a tattered dark red robe with a pale bone mask and "
    "long clawed hands. Exactly four full-body poses in a single horizontal row, evenly spaced, "
    "not touching each other, all the same size, all facing the viewer, feet on the same line: "
    "1) standing idle, 2) mid-step walking toward the viewer, 3) lunging with both claws raised, "
    "4) recoiling in pain. Chunky readable pixel art, strong dark outline, limited palette, "
    "lit from above. Background is one flat solid pure magenta colour (#FF00FF), no floor, "
    "no shadows on the ground, no text, no labels, no border."
)
# The re-roll prompt. It is sent together with take 1 as a reference image, so it only has
# to describe the CHANGE. Adjacent strings inside ( ) are joined into one long string by Python.
BRIGHTEN_PROMPT = (
    "Edit this sprite sheet. Keep the four poses, their positions, sizes and the pixel-art style "
    "exactly as they are. Change only the colours of the character so it reads against a very dark "
    "background: make the robe a bright saturated crimson with lighter orange-red highlights on the "
    "folds, make the bone mask and hands pale ivory, and keep a thin dark outline. "
    "Keep the background one flat solid pure magenta (#FF00FF). No text."
)
WALL_PROMPT = (
    "Seamless tileable square wall texture for a retro first-person shooter: damp grey-green "
    "dungeon stone blocks with dark mortar lines and a few cracks, flat front-on view, evenly lit, "
    "no perspective, no shadows cast from outside, chunky low-resolution pixel-art look, "
    "the left edge matches the right edge and the top edge matches the bottom edge. No text."
)
FOG_BG = "1c1f26"            # the level's fog colour: the readability gate tests against it


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("fps_2d", "nano-banana billboard sheet + tiling wall", CELL) as log:
        first = cell_lib.generate(log, CELL, "cultist", ENEMY_PROMPT, aspect="16:9")
        # Take 1 was on-model but failed the readability gate: dark robe on dark fog, contrast
        # 1.19 against a limit of 2.0. Take 2 is an EDIT of take 1 (the image goes back in as a
        # reference), which keeps the poses and only changes the colours.
        log.reroll("readability 1.19 on fog: the AI chose a dark palette for a dark level")
        log.add_step("review: rejected take 1", cell_lib.GLANCE_SECONDS, human=True)
        enemy_raw = cell_lib.generate(log, CELL, "cultist", BRIGHTEN_PROMPT, aspect="16:9", refs=(first,), take=2)
        wall_raw = cell_lib.generate(log, CELL, "wall", WALL_PROMPT, aspect="1:1")
        if "--generate-only" in sys.argv:
            return
        assets = CELL / "assets"
        # 192 px tall: an enemy 6 m away covers about that many screen pixels at 720p.
        cell_lib.cleanup(log, enemy_raw, assets / "cultist", "cultist", "--fit-height", "192", "--palette", "none")
        cell_lib.looked(log, "enemy sheet: four separate poses, same character")
        # Walls are 128 px squares: small enough to stay crisp-pixelated, cheap in a web build.
        cell_lib.cleanup(log, wall_raw, assets / "wall", "wall", "--single", "--no-snap", "--size", "128x128")
        cell_lib.looked(log, "wall texture: tiles without an obvious seam")
        with log.step("gates"):
            # The four poses are different actions, not one loop, so overlap between them is
            # reported with a low bar; feet must still share a baseline.
            log.add_gate(gate2d.run_gate(assets / "cultist", kind="sprite", target_height=96, bg=FOG_BG,
                                         iou_min=0.15, godot=cell_lib.godot_exe()))
            log.add_gate(gate2d.run_gate(assets / "wall" / "wall_00.png", kind="background", bg=FOG_BG,
                                         godot=cell_lib.godot_exe()))
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

"""metroidvania_2d/build.py - metroidvania cell, 2D art: a palette-locked pixel hero and cave tiles.

The cheap proven style: low-resolution pixel art snapped to ONE fixed 16-colour palette.
The palette is what makes separately generated pieces look like one game: the hero, the
ground tile and the rock tile are three different requests, but after snapping they share
exactly the same 16 colours. This is the Medusa's Price method with a different palette.

    python build.py            # re-runs are free: images are cached in raw/

Pipeline: 3 Nano Banana images -> art_cleanup (palette snap, hard edges) -> gate2d -> demo.tscn
(TileMapLayer + AnimatedSprite2D) -> screenshot.
"""
import pathlib
import sys

from PIL import Image

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

# "Sweetie 16" by GrafxKid: a free, widely used 16-colour pixel-art palette (from Lospec).
PALETTE = "1a1c2c,5d275d,b13e53,ef7d57,ffcd75,a7f070,38b764,257179,29366f,3b5dc9,41a6f6,73eff7,f4f4f4,94b0c2,566c86,333c57"
PALETTE_WORDS = ("Use only these colours: near-black navy, deep purple, crimson, orange, pale yellow, "
                 "lime green, green, teal, dark blue, blue, sky blue, cyan, white, pale grey-blue, slate, dark slate.")
HERO_PROMPT = (
    "Pixel art sprite sheet for a metroidvania hero, side view facing RIGHT in every frame: a small "
    "hooded wanderer in a pale grey-blue cloak with a long orange scarf, white face, short sword at "
    "the hip. Exactly six frames of a run cycle in ONE horizontal row, evenly spaced with wide "
    "gaps, not touching, all the same size, feet on the same ground line: contact, down, passing, "
    "contact with the other leg, down, passing. The scarf trails behind. Chunky low-resolution "
    "pixel art with a dark navy outline, flat colours, no gradients, no anti-aliasing. "
    + PALETTE_WORDS +
    " Background is one flat solid pure magenta colour (#FF00FF), no ground, no shadow, no text."
)
TOP_PROMPT = (
    "One square pixel-art terrain tile for a 2D side-view cave platformer: the top quarter is a "
    "bumpy strip of teal and green moss with a dark outline on its upper edge, the rest below is "
    "dark slate cave rock made of chunky stones. The left edge matches the right edge so it "
    "tiles horizontally. Flat front view, low resolution, flat colours, no gradients. "
    + PALETTE_WORDS + " No text, no border."
)
FILL_PROMPT = (
    "One square seamless pixel-art texture of dark slate cave rock made of chunky stones with "
    "near-black navy gaps, for a 2D side-view cave platformer. The left edge matches the right "
    "edge and the top edge matches the bottom edge. Flat front view, low resolution, flat colours, "
    "no gradients. " + PALETTE_WORDS + " No text, no border."
)
HERO_PX = 48             # hero height in the 320x180 world the camera shows (zoom 4)
TILE_PX = 32
# The far cave wall. Measured with gate2d --bg: on the palette's darkest colours the hero's
# dark legs and outline vanish (contrast 1.5); on mid slate the figure passes (2.4).
CAVE_BG = "566c86"


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("metroidvania_2d", "nano-banana run sheet + 2 tiles, one 16-colour palette", CELL) as log:
        hero_raw = cell_lib.generate(log, CELL, "wanderer_run", HERO_PROMPT, aspect="21:9")
        top_raw = cell_lib.generate(log, CELL, "tile_top", TOP_PROMPT, aspect="1:1")
        fill_raw = cell_lib.generate(log, CELL, "tile_fill", FILL_PROMPT, aspect="1:1")
        if "--generate-only" in sys.argv:
            return
        assets = CELL / "assets"
        # --hard-alpha: pixel art has no half-transparent edge pixels.
        result = cell_lib.cleanup(log, hero_raw, assets / "wanderer", "run", "--fit-height", str(HERO_PX),
                                  "--palette", PALETTE, "--hard-alpha")
        frames = len(result["cells"])
        cell_lib.looked(log, f"run sheet: {frames} frames, all facing right, legs alternate")
        if frames != 6:
            log.fail_mode(f"asked for 6 run frames, the slicer found {frames}")
        # Two things went wrong with the raw tiles, both fixed by cropping before the resize:
        #   top:  the AI drew a frame around the tile, which shows as a grid when repeated.
        #   fill: a 1024 px texture squeezed to 32 px turns "chunky stones" into grey noise.
        log.fail_mode("tile images come with a drawn border and far too much detail for 32 px")
        crops = {"top": (0.10, 0.02, 0.90, 0.82), "fill": (0.25, 0.25, 0.75, 0.75)}      # left, top, right, bottom
        for name, raw in (("top", top_raw), ("fill", fill_raw)):
            with log.step(f"crop {name}"):
                image = Image.open(raw)
                left, top, right, bottom = crops[name]
                cropped = cell_lib.ART_TESTS / "runs" / f"metroidvania_{name}_crop.png"
                cropped.parent.mkdir(exist_ok=True)
                image.crop((int(left * image.width), int(top * image.height),
                            int(right * image.width), int(bottom * image.height))).save(cropped)
            cell_lib.cleanup(log, cropped, assets / "tiles", name, "--single", "--palette", PALETTE,
                             "--size", f"{TILE_PX}x{TILE_PX}")
        log.add_step("pick crop boxes for the two tiles by eye", 120.0, human=True)
        with log.step("tile atlas"):
            # The TileSet wants one picture: ground tile at atlas (0,0), rock tile at (1,0).
            # The separately generated rock tile did not match the ground tile (different stone
            # size, stray coloured specks), so it is not used. The rock tile is made from the
            # ground tile instead: its lower, moss-free half stacked twice. Guaranteed to match.
            top_tile = Image.open(assets / "tiles" / "top_00.png")
            rock_half = top_tile.crop((0, TILE_PX // 2, TILE_PX, TILE_PX))
            atlas = Image.new("RGBA", (TILE_PX * 2, TILE_PX))
            atlas.paste(top_tile, (0, 0))
            atlas.paste(rock_half, (TILE_PX, 0))
            atlas.paste(rock_half, (TILE_PX, TILE_PX // 2))
            atlas.save(assets / "tiles" / "atlas.png")
        cell_lib.looked(log, "tiles: moss strip on top, rock matches between the two tiles")
        log.fail_mode("two tiles from two requests do not match each other: derive variants from ONE tile")
        with log.step("gates"):
            log.add_gate(gate2d.run_gate(assets / "wanderer", kind="sprite", palette=PALETTE, target_height=HERO_PX,
                                         bg=CAVE_BG, loop=True, side_view=True, godot="off"))
            log.add_gate(gate2d.run_gate(assets / "tiles" / "atlas.png", kind="tileset", palette=PALETTE,
                                         target_height=TILE_PX, bg=CAVE_BG, godot="off"))
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

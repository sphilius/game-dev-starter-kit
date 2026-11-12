"""test_art_cleanup.py - checks tools/art_cleanup.py on a fake sprite sheet.

Dev-only. No test framework needed: run it and it prints PASS or stops at the
first failed check with a message.
  python tools/test_art_cleanup.py

The fake sheet imitates a Nano Banana output: a magenta background, six poses in
two rows, slightly-off palette colours, soft (anti-aliased) edges, one pose with a
floating snake head that must stay part of that pose, and a stray speck that
must be ignored.
"""
import json
import pathlib
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

# Lets "import art_cleanup" find the tool sitting next to this file.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import art_cleanup  # noqa: E402  (the import has to come after the path line above)

MAGENTA = (255, 0, 255)
# Close to the palette black and terracotta, but not exact (like real AI output).
OFF_BLACK = (34, 26, 20)
OFF_TERRACOTTA = (205, 95, 64)
# Widths of the six poses in reading order, so the test can tell if the order is right.
WIDTHS = [60, 70, 80, 90, 100, 110]
# Supersampling: draw at 2x, then shrink, which gives the soft edges a real image has.
SS = 2


def make_sheet(path: pathlib.Path, background: tuple = MAGENTA, body: tuple = OFF_BLACK,
               stripe: tuple = OFF_TERRACOTTA) -> None:
    """Draws the fake sheet and saves it to `path`. The colours are parameters so the same
    sheet can be drawn on a green screen with a different palette."""
    OFF_BLACK, OFF_TERRACOTTA = body, stripe      # local names hide the module constants below
    w, h = 1600, 800
    img = Image.new("RGB", (w * SS, h * SS), background)
    draw = ImageDraw.Draw(img)
    for i, width in enumerate(WIDTHS):
        row, col = divmod(i, 3)  # divmod gives (i // 3, i % 3): row 0 or 1, column 0 to 2
        left = 150 + col * 480
        # Row 2 poses are taller and sit at slightly different heights, to test row grouping.
        height = 200 + row * 60 + col * 10
        bottom = 330 + row * 400 + col * 8
        top = bottom - height
        draw.rectangle([left * SS, top * SS, (left + width) * SS, bottom * SS], fill=OFF_BLACK)
        # An incised terracotta stripe across the body.
        draw.rectangle([(left + 8) * SS, (top + 40) * SS, (left + width - 8) * SS, (top + 46) * SS],
                       fill=OFF_TERRACOTTA)
        if i == 0:
            # A floating snake head 3 px above the body: must merge into pose 0 (default --gap is 6).
            draw.ellipse([(left + 20) * SS, (top - 23) * SS, (left + 40) * SS, (top - 3) * SS],
                         fill=OFF_BLACK)
    # A 3x3 speck far from everything: must be dropped (default --min-area is 200).
    draw.rectangle([800 * SS, 30 * SS, 803 * SS, 33 * SS], fill=OFF_BLACK)
    img.resize((w, h), Image.LANCZOS).save(path)


def make_portrait(path: pathlib.Path) -> None:
    """A painted-looking circle (many colours) on magenta, like a portrait stage."""
    size = 512
    yy, xx = np.mgrid[0:size, 0:size]
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    rgb[...] = MAGENTA
    inside = (xx - size / 2) ** 2 + (yy - size / 2) ** 2 < (size * 0.48) ** 2
    rgb[inside] = np.stack([60 + xx[inside] % 120, 90 + yy[inside] % 80, np.full(inside.sum(), 40)], axis=-1)
    Image.fromarray(rgb).save(path)


def check(condition: bool, message: str) -> None:
    """Stops the test with a clear message when a check fails."""
    if not condition:
        sys.exit(f"FAIL: {message}")


def test_sheet(tmp: pathlib.Path) -> None:
    """Runs the tool on the fake sheet and checks every promise it makes for sprite sheets:
    right pose count, reading order, merged snake head, equal cells, palette-only
    colours, feet on one point, strip and meta files, and a reusable scale.
    `tmp` is the scratch folder to write into.
    """
    raw = tmp / "sheet.png"
    make_sheet(raw)
    out = tmp / "out"
    result = art_cleanup.main([str(raw), "--name", "fake", "--out", str(out), "--fit-height", "128"])

    check(len(result["cells"]) == 6, f"expected 6 poses, found {len(result['cells'])} (speck kept or head split off?)")

    widths = [b[2] - b[0] for b in result["source_boxes"]]
    check(widths == sorted(widths), f"poses not in reading order: widths {widths}")

    first_height = result["source_boxes"][0][3] - result["source_boxes"][0][1]
    check(first_height > 220, f"floating snake head was not merged into pose 0 (height {first_height})")

    cell_w, cell_h = result["cell_size"]
    sizes = {c.size for c in result["cells"]}
    check(sizes == {(cell_w, cell_h)}, f"cells differ in size: {sizes}")
    check(cell_h - 2 * 2 in (127, 128, 129), f"tallest pose should be about 128 px, cell is {cell_h}")

    # A set comprehension: the palette as a set of (r, g, b) tuples, so "<=" can ask
    # "is every colour in this frame also in the palette?" in one step.
    palette = {tuple(c) for c in art_cleanup.PALETTE_VASE.tolist()}
    feet_x, feet_y = result["feet"]
    for i, cell in enumerate(result["cells"]):
        px = np.array(cell)
        visible = px[..., 3] > 0
        colours = {tuple(c) for c in px[visible][:, :3].tolist()}
        check(colours <= palette, f"frame {i} has off-palette colours: {colours - palette}")
        check(visible[feet_y - 1].any(), f"frame {i}: feet are not on the baseline")
        check(visible[feet_y - 1, feet_x - 3:feet_x + 3].any(), f"frame {i}: not centred on the feet anchor")

    strip = Image.open(out / "fake_strip.png")
    check(strip.size == (cell_w * 6, cell_h), f"strip is {strip.size}, expected {(cell_w * 6, cell_h)}")
    meta = json.loads((out / "fake_meta.json").read_text())
    check(meta["frames"] == 6 and meta["cell_size"] == [cell_w, cell_h], f"meta is wrong: {meta}")
    check((out / "fake_05.png").exists(), "frame files were not written")

    # A second run with the printed scale must give the same cell size (sibling sheets match).
    again = art_cleanup.main([str(raw), "--name", "fake2", "--out", str(out),
                              "--scale", f"{result['scale']:.5f}"])
    check(again["cell_size"] == result["cell_size"], "reusing --scale gave a different size")


def test_portrait(tmp: pathlib.Path) -> None:
    """Checks --single mode the way portraits use it: exact size, magenta gone,
    and with --no-snap the painting keeps all its colours (it is not a vase sprite).
    """
    raw = tmp / "portrait.png"
    make_portrait(raw)
    result = art_cleanup.main([str(raw), "--name", "por", "--out", str(tmp / "por"),
                               "--single", "--no-snap", "--size", "64x64"])
    px = np.array(result["cells"][0])
    check(px.shape[:2] == (64, 64), f"portrait is {px.shape[:2]}, expected 64x64")
    check(px[0, 0, 3] == 0, "magenta corner was not made transparent")
    check(px[32, 32, 3] == 255, "centre of the painting should be solid")
    check(len({tuple(c) for c in px[px[..., 3] > 0][:, :3].tolist()}) > 6,
          "--no-snap should keep the painting's many colours")


def test_green_key_and_custom_palette(tmp: pathlib.Path) -> None:
    """The two options added for the jam kits: a green background (--key-color) and a palette
    given on the command line (--palette). Colours must snap to THAT palette, not the vase one.
    """
    raw = tmp / "green.png"
    make_sheet(raw, background=(0, 255, 0), body=(40, 44, 90), stripe=(240, 200, 70))
    result = art_cleanup.main([str(raw), "--name", "green", "--out", str(tmp / "green"),
                               "--fit-height", "96", "--key-color", "green",
                               "--palette", "262b5c,f2c744,ffffff"])
    check(len(result["cells"]) == 6, f"green key: expected 6 poses, found {len(result['cells'])}")
    wanted = {(0x26, 0x2B, 0x5C), (0xF2, 0xC7, 0x44), (0xFF, 0xFF, 0xFF)}
    for i, cell in enumerate(result["cells"]):
        px = np.array(cell)
        colours = {tuple(c) for c in px[px[..., 3] > 0][:, :3].tolist()}
        check(colours <= wanted, f"green frame {i} has colours outside the custom palette: {colours - wanted}")


def test_despill(tmp: pathlib.Path) -> None:
    """Full-colour art (--palette none) loses its pink outline; --no-despill keeps it."""
    # A grey square with a 2 px ring of half-magenta around it, like an AI-blended outline.
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    img[...] = (255, 0, 255)
    img[18:62, 18:62] = (190, 70, 190)          # the halo: grey mixed with magenta
    img[20:60, 20:60] = (120, 120, 120)         # the figure
    raw = tmp / "halo.png"
    Image.fromarray(img).save(raw)
    key = (255, 0, 255)

    def worst_tint(folder: str, *flags: str) -> int:
        """Runs the tool and returns the strongest key-ness left on any visible pixel."""
        art_cleanup.main([str(raw), "--name", "halo", "--out", str(tmp / folder), "--single",
                          "--palette", "none", "--key-threshold", "200", *flags])
        out = np.array(Image.open(tmp / folder / "halo_00.png").convert("RGBA")).astype(np.int32)
        return int(art_cleanup.key_ness(out[..., :3], key)[out[..., 3] > 0].max())

    check(worst_tint("kept", "--no-despill") >= 100, "without despill the halo should still be pink")
    check(worst_tint("clean") <= 0, "despill should leave no key tint on the outline")


def test_palette_files(tmp: pathlib.Path) -> None:
    """Palettes load from a Lospec .hex file and a GIMP .gpl file; "none" turns snapping off."""
    hex_file = tmp / "p.hex"
    hex_file.write_text("1a1c2c\n5d275d\n\nb13e53\n")
    gpl_file = tmp / "p.gpl"
    gpl_file.write_text("GIMP Palette\nName: test\n#\n26 28 44 dark\n255 205 117 gold\n")
    check(art_cleanup.load_palette(str(hex_file)).tolist() == [[0x1A, 0x1C, 0x2C], [0x5D, 0x27, 0x5D], [0xB1, 0x3E, 0x53]],
          ".hex palette parsed wrong")
    check(art_cleanup.load_palette(str(gpl_file)).tolist() == [[26, 28, 44], [255, 205, 117]], ".gpl palette parsed wrong")
    check(art_cleanup.load_palette("none") is None, "'none' should disable snapping")
    check(art_cleanup.load_key_colour("00FF00") == (0, 255, 0), "hex key colour parsed wrong")


if __name__ == "__main__":
    # "with" opens a temporary folder and deletes it again when the block ends, even on failure.
    with tempfile.TemporaryDirectory() as folder:
        test_sheet(pathlib.Path(folder))
        test_portrait(pathlib.Path(folder))
        test_green_key_and_custom_palette(pathlib.Path(folder))
        test_palette_files(pathlib.Path(folder))
        test_despill(pathlib.Path(folder))
    print("PASS")

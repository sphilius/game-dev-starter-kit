"""art_cleanup.py - turns a raw Nano Banana image into clean game-ready PNGs.

Dev-only tool (never shipped in the game). Lifted from Medusa's Price and made generic:
the palette and the key colour are now options instead of being hardcoded.

  1. Key out the flat background colour (--key-color, default magenta) -> transparent.
  2. Snap every visible pixel to a palette (--palette; kills AI colour drift and fuzz).
  3. Slice a sprite sheet into frames: every separate blob of pixels is one pose,
     read left to right, top to bottom.
  4. Scale the frames and line them up on equal-sized cells, feet on the bottom
     edge, so an AnimatedSprite2D does not jitter between frames.

Usage (run from the project root):
  Sprite sheet, Medusa 2x size (128 px tall frames):
    python tools/art_cleanup.py raw/medusa_a.png --name medusa_a --fit-height 128
  Second sheet of the same character, same scale as the first (copy the scale it printed):
    python tools/art_cleanup.py raw/medusa_b.png --name medusa_b --scale 0.1667
  Portrait painting (no slicing, no palette snap, exact size):
    python tools/art_cleanup.py raw/portrait_1.png --name portrait_1 --single --no-snap --size 128x128
  Background (no slicing, 720 px tall):
    python tools/art_cleanup.py raw/bg_temple.png --name bg_temple --single --fit-height 720

Palettes (--palette):
    vase                      the built-in 6-colour Medusa palette (the default)
    none                      keep the image's own colours (same as --no-snap)
    1a1410,c8643b,f2efe8      a comma-separated list of hex colours
    my_palette.hex            a file with one hex colour per line (Lospec ".hex" export);
                              a GIMP .gpl palette file also works
Key colours (--key-color): magenta (default), green, blue, cyan, or a hex colour such as 00ff00.

Output goes to ./processed/<name>/ unless you pass --out:
  <name>_00.png, <name>_01.png ...  one file per frame (all the same size)
  <name>_strip.png                  all frames side by side (Sprite2D hframes = frame count)
  <name>_meta.json                  scale, cell size, feet anchor, frame count
"""
import argparse
import json
import pathlib
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

# The built-in palette (Medusa's Price, Greek vase colours). Used when --palette is "vase".
# Every visible pixel gets moved to the closest of these colours.
PALETTE_VASE = np.array([
    (0x1A, 0x14, 0x10),  # black: living bodies
    (0xC8, 0x64, 0x3B),  # terracotta: clay, incised lines
    (0x7A, 0x3A, 0x22),  # clay dark: terrain, architecture
    (0xE2, 0xA2, 0x7A),  # clay pale: far background
    (0xF2, 0xEF, 0xE8),  # marble: stone
    (0xE8, 0xB5, 0x47),  # gold: danger and power
], dtype=np.int32)

# Folder the results go to when --out is not given (relative to the project root).
DEFAULT_OUT = pathlib.Path.cwd() / "processed"

# Named key colours for --key-color. Bright, saturated colours that never appear in a sprite.
KEY_COLOURS = {"magenta": (255, 0, 255), "green": (0, 255, 0), "blue": (0, 0, 255), "cyan": (0, 255, 255)}

# Fraction of a frame's height, measured up from its lowest pixel, that counts as
# "the feet" when lining frames up (see feet_anchor_x).
FEET_BAND = 0.25


def parse_hex(text: str) -> tuple[int, int, int]:
    """Turns "c8643b" or "#C8643B" into (200, 100, 59)."""
    text = text.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a 6-digit hex colour: {text!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def load_palette(spec: str) -> np.ndarray | None:
    """Turns a --palette value into an (N, 3) array of colours, or None for "none".

    Accepts "vase", "none", a comma-separated hex list, a .hex file (one colour per
    line) or a GIMP .gpl file (lines of "R G B name").
    """
    if spec == "vase":
        return PALETTE_VASE
    if spec == "none":
        return None
    path = pathlib.Path(spec)
    colours: list[tuple[int, int, int]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue                          # blank line
            if len(parts) >= 3 and all(part.isdigit() for part in parts[:3]):
                colours.append((int(parts[0]), int(parts[1]), int(parts[2])))   # .gpl row "R G B name"
                continue
            try:
                colours.append(parse_hex(parts[0]))                             # .hex row
            except ValueError:
                continue                          # headers and comments ("GIMP Palette", "Name: x", "#")
    else:
        colours = [parse_hex(part) for part in spec.split(",") if part.strip()]
    if not colours:
        raise ValueError(f"--palette {spec!r}: no colours found")
    return np.array(colours, dtype=np.int32)


def load_key_colour(spec: str) -> tuple[int, int, int]:
    """Turns a --key-color value (a name from KEY_COLOURS or a hex colour) into (r, g, b)."""
    return KEY_COLOURS[spec.lower()] if spec.lower() in KEY_COLOURS else parse_hex(spec)


def key_ness(rgb: np.ndarray, key: tuple[int, int, int]) -> np.ndarray:
    """How much each pixel looks like the key colour: about 255 for the key itself, 0 or less for art.

    For a pure key (every channel 0 or 255, e.g. magenta 255,0,255 or green 0,255,0):
        key-ness = (lowest of the channels the key has ON) - (highest of the channels it has OFF)
    Magenta gives min(red, blue) - green: Medusa's original formula. This beats plain colour
    distance because it also catches the half-blended fringe around shapes.
    For any other key colour it falls back to 255 minus twice the colour distance.
    rgb is an (height, width, 3) int32 array.
    """
    on = [i for i in range(3) if key[i] >= 250]
    off = [i for i in range(3) if key[i] <= 5]
    if on and off and len(on) + len(off) == 3:
        return rgb[..., on].min(axis=-1) - rgb[..., off].max(axis=-1)
    distance = np.sqrt(((rgb - np.array(key, dtype=np.int32)) ** 2).sum(axis=-1))
    return (255 - distance * 2).astype(np.int32)


def key_out(rgba: np.ndarray, key: tuple[int, int, int], threshold: int) -> np.ndarray:
    """Makes the key-coloured background (and the fringe around shapes) transparent.

    Any pixel whose key-ness (see key_ness) is >= threshold gets alpha 0. A new array is returned.
    """
    out = rgba.copy()
    out[key_ness(out[..., :3].astype(np.int32), key) >= threshold, 3] = 0
    return out


def key_magenta(rgba: np.ndarray, threshold: int) -> np.ndarray:
    """Makes the magenta background (and the pink fringe around shapes) transparent.

    "Magenta-ness" = min(red, blue) - green. Pure magenta scores 255. Every palette
    colour scores 0 or below (they all have more green than red or blue), so any
    pixel scoring >= threshold is background or edge fringe and gets alpha 0.
    rgba is an (height, width, 4) uint8 array; a new array is returned.
    """
    out = rgba.copy()
    rgb = out[..., :3].astype(np.int32)
    magenta_ness = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
    out[magenta_ness >= threshold, 3] = 0
    return out


def snap_to_palette(rgba: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Moves the colour of every visible pixel to the nearest palette colour.

    Transparency is left alone, so soft edges stay soft. "Nearest" is the plain
    distance in red-green-blue space. One palette colour is tried at a time
    (instead of all at once) to keep memory use small on 4K images.
    """
    out = rgba.copy()
    rgb = out[..., :3].astype(np.int32)
    best_dist = np.full(rgb.shape[:2], np.iinfo(np.int32).max, dtype=np.int32)
    best_idx = np.zeros(rgb.shape[:2], dtype=np.int32)
    for i, colour in enumerate(palette):
        dist = ((rgb - colour) ** 2).sum(axis=-1)
        closer = dist < best_dist
        best_dist[closer] = dist[closer]
        best_idx[closer] = i
    visible = out[..., 3] > 0
    out[visible, :3] = palette[best_idx[visible]].astype(np.uint8)
    return out


def find_frames(alpha: np.ndarray, gap: int, min_area: int) -> list[np.ndarray]:
    """Finds each separate pose in a sheet and returns one boolean mask per pose.

    A pose can be made of several unconnected bits (a snake head floating just
    off the hair), so the visible area is first grown by `gap` pixels: bits closer
    than that merge into one blob. Each blob's mask is then cut back to the real
    pixels. Blobs smaller than `min_area` pixels are stray specks and are dropped.
    Masks come back in reading order: rows top to bottom, then left to right.
    """
    visible = alpha > 0
    grown = ndimage.binary_dilation(visible, iterations=gap) if gap > 0 else visible
    labels, count = ndimage.label(grown)
    frames = []
    for blob_id in range(1, count + 1):
        mask = (labels == blob_id) & visible
        if mask.sum() >= min_area:
            frames.append(mask)
    return sort_reading_order(frames)


def bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    """The (left, top, right, bottom) box around a mask's True pixels (right/bottom exclusive)."""
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def sort_reading_order(masks: list[np.ndarray]) -> list[np.ndarray]:
    """Orders poses like text: top row first, each row left to right.

    Poses are taken from the top down. A pose joins the current row when its
    vertical middle falls inside the row's top-to-bottom span; otherwise it
    starts a new row. Poses of different heights still land in the right row.
    """
    # A generator expression builds (box, mask) pairs; key=lambda sorts them by the box's top edge.
    boxed = sorted(((bbox(m), m) for m in masks), key=lambda item: item[0][1])
    rows: list[list] = []
    row_top = row_bottom = None
    for box, mask in boxed:
        middle = (box[1] + box[3]) / 2.0
        if rows and row_top <= middle <= row_bottom:
            rows[-1].append((box, mask))
            row_bottom = max(row_bottom, box[3])
        else:
            rows.append([(box, mask)])
            row_top, row_bottom = box[1], box[3]
    ordered = []
    for row in rows:
        ordered.extend(mask for _, mask in sorted(row, key=lambda item: item[0][0]))
    return ordered


def resize_rgba(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resizes with transparency handled correctly.

    "RGBa" (small a) is Pillow's premultiplied mode: colour is multiplied by
    alpha first, so the invisible magenta never bleeds into the edges when
    pixels are blended during the resize.
    """
    size = (max(1, size[0]), max(1, size[1]))
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def feet_anchor_x(alpha: np.ndarray) -> int:
    """The x position of the feet: the middle of the pixels in the lowest quarter of the frame.

    Lining frames up on this (instead of the box centre) keeps the body still when
    the box grows, for example when the snakes lash out in front of her.
    """
    rows = np.flatnonzero((alpha > 0).any(axis=1))
    band_top = rows[-1] - int((rows[-1] - rows[0]) * FEET_BAND)
    ys, xs = np.nonzero(alpha[band_top:] > 0)
    return int(round(xs.mean()))


def process_sheet(rgba: np.ndarray, args: argparse.Namespace) -> dict:
    """Slices, scales and aligns a sprite sheet. Returns the frames and their layout."""
    masks = find_frames(rgba[..., 3], args.gap, args.min_area)
    if not masks:
        raise ValueError("no poses found: is the background magenta? try a lower --key-threshold")
    boxes = [bbox(m) for m in masks]

    # One scale for every frame, so the character stays the same size in every pose.
    scale = args.scale if args.scale else args.fit_height / max(b[3] - b[1] for b in boxes)

    frames = []
    # zip walks both lists side by side; "(left, top, right, bottom)" unpacks each box tuple.
    for mask, (left, top, right, bottom) in zip(masks, boxes):
        # Cut out only this pose: pixels that belong to a neighbouring pose become clear.
        crop = rgba[top:bottom, left:right].copy()
        crop[~mask[top:bottom, left:right], 3] = 0
        img = resize_rgba(Image.fromarray(crop),
                          (round((right - left) * scale), round((bottom - top) * scale)))
        frames.append(np.array(img))

    # Resizing blends colours at the edges; snap again so only palette colours remain.
    # "[... for f in frames]" is a list comprehension: a new list with each frame snapped.
    if not args.no_snap:
        frames = [snap_to_palette(f, args.palette_rgb) for f in frames]
    if args.hard_alpha:
        for f in frames:
            f[..., 3] = np.where(f[..., 3] >= 128, 255, 0)

    # Every cell is the same size: wide enough for the farthest reach left and right
    # of the feet in any frame, tall enough for the tallest frame.
    anchors = [feet_anchor_x(f[..., 3]) for f in frames]
    reach_left = max(anchors)
    reach_right = max(f.shape[1] - a for f, a in zip(frames, anchors))
    pad = args.pad
    cell_w = reach_left + reach_right + 2 * pad
    cell_h = max(f.shape[0] for f in frames) + 2 * pad
    feet = (pad + reach_left, cell_h - pad)

    cells = []
    for f, anchor in zip(frames, anchors):
        cell = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
        # Feet line up on one point in every cell, bottom edge of the pose on the baseline.
        cell.paste(Image.fromarray(f), (feet[0] - anchor, feet[1] - f.shape[0]))
        cells.append(cell)

    return {"cells": cells, "scale": scale, "cell_size": (cell_w, cell_h),
            "feet": feet, "source_boxes": boxes}


def process_single(rgba: np.ndarray, args: argparse.Namespace) -> dict:
    """One image, no slicing: key, snap (unless --no-snap) and resize. For portraits and backgrounds."""
    h, w = rgba.shape[:2]
    if args.size:
        size = args.size
    elif args.scale:
        size = (round(w * args.scale), round(h * args.scale))
    elif args.fit_height:
        size = (round(w * args.fit_height / h), args.fit_height)
    else:
        size = (w, h)
    img = np.array(resize_rgba(Image.fromarray(rgba), size))
    if not args.no_snap:
        img = snap_to_palette(img, args.palette_rgb)
    return {"cells": [Image.fromarray(img)], "scale": size[1] / h, "cell_size": size,
            "feet": None, "source_boxes": [(0, 0, w, h)]}


def save(result: dict, out_dir: pathlib.Path, name: str) -> None:
    """Writes the frame PNGs, the strip and the meta JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = result["cells"]
    for i, cell in enumerate(cells):
        cell.save(out_dir / f"{name}_{i:02d}.png")
    cell_w, cell_h = result["cell_size"]
    strip = Image.new("RGBA", (cell_w * len(cells), cell_h), (0, 0, 0, 0))
    for i, cell in enumerate(cells):
        strip.paste(cell, (i * cell_w, 0))
    strip.save(out_dir / f"{name}_strip.png")
    meta = {"frames": len(cells), "scale": round(result["scale"], 5),
            "cell_size": [cell_w, cell_h], "feet": result["feet"]}
    (out_dir / f"{name}_meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def parse_size(text: str) -> tuple[int, int]:
    """Turns "128x128" into (128, 128)."""
    w, h = text.lower().split("x")
    return int(w), int(h)


def build_parser() -> argparse.ArgumentParser:
    """Describes every command-line option (argparse turns "--fit-height 128" into args.fit_height).

    argparse also writes the --help text from the help= strings, so
    "python tools/art_cleanup.py --help" lists everything below.
    A "mutually exclusive group" means you may pass at most one of its options.
    """
    parser = argparse.ArgumentParser(description="Clean up a Nano Banana image for the game.")
    parser.add_argument("input", type=pathlib.Path, help="raw PNG from Nano Banana")
    parser.add_argument("--name", required=True, help="base name for the output files")
    parser.add_argument("--out", type=pathlib.Path, default=None,
                        help="output folder (default art/processed/<name>)")
    size = parser.add_mutually_exclusive_group()
    size.add_argument("--scale", type=float, help="exact scale factor (reuse one printed earlier)")
    size.add_argument("--fit-height", type=int, help="scale so the tallest pose is this many px")
    size.add_argument("--size", type=parse_size, help="single mode only: exact WxH, e.g. 128x128")
    parser.add_argument("--single", action="store_true", help="one image, do not slice")
    parser.add_argument("--no-snap", action="store_true", help="keep original colours (portraits)")
    parser.add_argument("--palette", default="vase",
                        help="vase | none | hex list 'aabbcc,ddeeff' | .hex or .gpl file (default vase)")
    parser.add_argument("--key-color", default="magenta",
                        help="background colour to remove: magenta | green | blue | cyan | hex (default magenta)")
    parser.add_argument("--hard-alpha", action="store_true", help="edges fully on or off, no soft edge")
    parser.add_argument("--key-threshold", type=int, default=60,
                        help="magenta-ness at which a pixel turns clear (lower = removes more)")
    parser.add_argument("--gap", type=int, default=6,
                        help="bits of one pose closer than this many px count as one pose")
    parser.add_argument("--min-area", type=int, default=200, help="ignore specks smaller than this (px)")
    parser.add_argument("--pad", type=int, default=2, help="clear border around each cell (px)")
    return parser


def main(argv: list[str] | None = None) -> dict:
    """Runs the whole cleanup: read, key, snap, slice or resize, save, report.

    argv is the list of command-line words. None means "use the real command line";
    the test passes its own list instead, so it can run the tool without a terminal.
    The result is returned too, so the test can check it.
    """
    args = build_parser().parse_args(argv)
    if args.size and not args.single:
        sys.exit("--size only works with --single (sheets use --scale or --fit-height)")
    if not args.single and not (args.scale or args.fit_height):
        sys.exit("sprite sheets need --scale or --fit-height")

    # Resolve the palette once. "--palette none" and "--no-snap" mean the same thing.
    args.palette_rgb = None if args.no_snap else load_palette(args.palette)
    args.no_snap = args.palette_rgb is None

    rgba = np.array(Image.open(args.input).convert("RGBA"))
    rgba = key_out(rgba, load_key_colour(args.key_color), args.key_threshold)
    # The snap before slicing makes the frame search see clean shapes; sheets snap again after resizing.
    if not args.no_snap:
        rgba = snap_to_palette(rgba, args.palette_rgb)
    result = process_single(rgba, args) if args.single else process_sheet(rgba, args)

    out_dir = args.out if args.out else DEFAULT_OUT / args.name
    save(result, out_dir, args.name)
    cell_w, cell_h = result["cell_size"]
    print(f"{len(result['cells'])} frame(s), cell {cell_w}x{cell_h}, scale {result['scale']:.5f} -> {out_dir}")
    if result["feet"]:
        print(f"feet at {tuple(result['feet'])} in each cell; sibling sheets: --scale {result['scale']:.5f}")
    return result


if __name__ == "__main__":
    main()

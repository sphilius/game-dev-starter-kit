"""build_sprites.py - turns art/processed/ into the game-ready art the scenes load.

Dev-only tool (never shipped). Run it from the project root after art_cleanup.py:
    python tools/build_sprites.py
then let Godot import the new files:
    godot --headless --path . --import

Why this step exists:
  art_cleanup.py gives every SHEET its own cell size and feet point. One character
  can use two sheets (Medusa has medusa_a and medusa_b), but an AnimatedSprite2D has
  only ONE offset. So here every frame of a character is pasted onto one shared
  canvas with the feet on the same pixel. Each frame stays its own PNG, which also
  keeps a shader's UV at 0..1 per frame (the petrify shader needs that).

What it writes (art/processed/ is ignored by Godot through its .gdignore):
  art/sprites/<char>/<sheet>_<NN>.png   padded frames
  art/sprites/<char>/<char>_frames.tres SpriteFrames with the named animations
  art/sprites/<char>/<char>_meta.json   canvas size, feet point, figure height
  art/sprites/{weapons,whip,statues,props}/*.png   single trimmed sprites
  art/portrait/stage_1..5.png, art/bg/level_N_{bg,px}.png, art/cards/*.png,
  art/tiles/terrain_<biome>.png
"""
import json
import pathlib
import shutil

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "art" / "processed"
ART = ROOT / "art"

# Each character: which processed sheets it uses, and its animations.
# An animation is (name, [(sheet, frame index), ...], default fps, loops?).
# The fps here is only the default stored in the .tres; the game sets the real
# speeds from Balance.ANIM_FPS_* at startup.
CHARACTERS: dict = {
    "medusa": [
        ("idle", [("medusa_a", 0), ("medusa_a", 1)], 2.0, True),
        # Stride, passing, stride, passing. Frame 3 (a crouched hop) is left out: in the
        # 2-5 order it read as a stutter-step (playtest, 2026-11-05).
        ("run", [("medusa_a", i) for i in (2, 4, 5, 4)], 10.0, True),
        ("jump", [("medusa_a", 6)], 1.0, False),
        ("fall", [("medusa_a", 7)], 1.0, False),
        # The whip has 8 frames that follow whip.gd's own timeline (speed 0 here:
        # the player sets the frame from the whip's frame_changed signal).
        # The sheet has 3 body poses: wind-up, strike, recovery.
        ("whip", [("medusa_b", i) for i in (0, 0, 1, 1, 1, 2, 2, 2)], 0.0, False),
        ("gaze", [("medusa_b", 3)], 1.0, False),
        ("hurt", [("medusa_b", 4)], 1.0, False),
        ("push", [("medusa_b", 5)], 1.0, False),
        ("kneel", [("medusa_b", 6)], 1.0, False),
        ("death", [("medusa_b", 7)], 1.0, False),
    ],
    "hoplite": [
        # Stride, high-knee passing, stride, passing. Frame 1 (a low lunge) made the
        # head bob and read as a stutter-step; the same goes for the next two sheets.
        ("walk", [("enemy_hoplites", i) for i in (0, 3, 2, 3)], 6.0, True),
        ("windup", [("enemy_hoplites", 4)], 1.0, False),
        ("thrust", [("enemy_hoplites", 5)], 1.0, False),
        ("recover", [("enemy_hoplites", 6)], 1.0, False),
        ("stagger", [("enemy_hoplites", 7)], 1.0, False),
    ],
    "eye_shading": [
        ("walk", [("enemy_hoplites_eyeshaded", i) for i in (0, 3, 2, 3)], 6.0, True),
        ("windup", [("enemy_hoplites_eyeshaded", 4)], 1.0, False),
        ("thrust", [("enemy_hoplites_eyeshaded", 5)], 1.0, False),
        ("recover", [("enemy_hoplites_eyeshaded", 6)], 1.0, False),
        ("stagger", [("enemy_hoplites_eyeshaded", 7)], 1.0, False),
    ],
    "leaper": [
        ("wait", [("enemy_leaper", 0)], 1.0, False),
        ("tense", [("enemy_leaper", 1)], 1.0, False),
        ("takeoff", [("enemy_leaper", 2)], 1.0, False),
        ("leap", [("enemy_leaper", 3)], 1.0, False),
        ("land", [("enemy_leaper", 4)], 1.0, False),
        ("stagger", [("enemy_leaper", 5)], 1.0, False),
    ],
    "archer": [
        ("idle", [("enemy_archer", 0), ("enemy_archer", 1)], 2.0, True),
        ("reach", [("enemy_archer", 2)], 1.0, False),
        ("nock", [("enemy_archer", 3)], 1.0, False),
        ("draw", [("enemy_archer", 4)], 1.0, False),
        ("release", [("enemy_archer", 5)], 1.0, False),
        ("cooldown", [("enemy_archer", 6)], 1.0, False),
        ("stagger", [("enemy_archer", 7)], 1.0, False),
    ],
    "mirror_bearer": [
        ("walk", [("enemy_mirror", i) for i in (0, 3, 2, 3)], 6.0, True),
        ("braced", [("enemy_mirror", 4)], 1.0, False),
        ("knocked", [("enemy_mirror", 5)], 1.0, False),
        ("stagger", [("enemy_mirror", 6)], 1.0, False),
        ("idle", [("enemy_mirror", 7)], 1.0, False),
    ],
    "perseus": [
        ("hover", [("enemy_perseus", 0), ("enemy_perseus", 1)], 6.0, True),
        ("dive", [("enemy_perseus", 2)], 1.0, False),
        ("grounded", [("enemy_perseus", 3)], 1.0, False),
        ("slash", [("enemy_perseus", 4)], 1.0, False),
        ("shield_down", [("enemy_perseus", 5)], 1.0, False),
        ("bash", [("enemy_perseus", 6)], 1.0, False),
        ("defeated", [("enemy_perseus", 7)], 1.0, False),
    ],
}

# Single sprites: (processed sheet, frame index, output folder, output name).
SINGLES = [
    ("weapons", 0, "sprites/weapons", "spear"),
    ("weapons", 1, "sprites/weapons", "arrow"),
    ("weapons", 2, "sprites/weapons", "mirror"),
    ("weapons", 3, "sprites/weapons", "shield"),
    ("whip_snake", 0, "sprites/whip", "snake_0"),
    ("whip_snake", 1, "sprites/whip", "snake_1"),
    ("whip_snake", 2, "sprites/whip", "snake_2"),
    ("statues", 0, "sprites/statues", "victim_0"),
    ("statues", 1, "sprites/statues", "victim_1"),
    ("statues", 2, "sprites/statues", "victim_2"),
    ("statues", 3, "sprites/statues", "victim_3"),
    ("statues", 5, "sprites/statues", "rubble"),
    ("level_props", 0, "sprites/props", "pool"),
    ("level_props", 1, "sprites/props", "torch_bracket"),
    ("level_props", 2, "sprites/props", "pennant"),
    ("level_props", 3, "sprites/props", "pressure_plate"),
    ("level_props", 4, "sprites/props", "exit_door"),
    ("level_props", 5, "sprites/props", "column"),
    ("level_props", 6, "sprites/props", "stalactite"),
    ("level_props", 7, "sprites/props", "amphora"),
    ("logo", 0, "cards", "logo"),
]

# Whole images copied as they are: (processed name, output path under art/).
COPIES = [(f"portrait_{n}", f"portrait/stage_{n}.png") for n in range(1, 6)]
COPIES += [(f"level_{n}_bg", f"bg/level_{n}_bg.png") for n in range(1, 5)]
COPIES += [(f"level_{n}_px", f"bg/level_{n}_px.png") for n in range(1, 5)]
COPIES += [
    ("title_card", "cards/title.png"),
    ("end_card", "cards/end.png"),
    ("vase_fallback", "cards/vase_fallback.png"),
    ("tile_temple", "tiles/terrain_temple.png"),
    ("tile_cliffs", "tiles/terrain_cliffs.png"),
    ("tile_cave", "tiles/terrain_cave.png"),
]


def frame_path(sheet: str, index: int) -> pathlib.Path:
    """Path of one processed frame, e.g. art/processed/medusa_a/medusa_a_03.png."""
    return PROCESSED / sheet / f"{sheet}_{index:02d}.png"


def load_meta(sheet: str) -> dict:
    """The cell size and feet point art_cleanup.py wrote for a sheet."""
    return json.loads((PROCESSED / sheet / f"{sheet}_meta.json").read_text())


def torso_x(img: Image.Image) -> float:
    """Horizontal middle of the torso: the alpha-weighted mean x of the band from 25%
    to 55% down the figure (below the head and hair, above the legs)."""
    box = img.getbbox()
    top = box[1] + (box[3] - box[1]) * 0.25
    bottom = box[1] + (box[3] - box[1]) * 0.55
    band = img.getchannel("A").crop((0, int(top), img.width, int(bottom)))
    # getdata() lists every pixel's alpha row by row; i % width is that pixel's x.
    total = weighted = 0
    for i, a in enumerate(band.getdata()):
        total += a
        weighted += a * (i % band.width)
    return weighted / total if total else img.width / 2


def build_character(name: str, anims: list) -> dict:
    """Pads all frames of one character onto a shared canvas and writes its SpriteFrames."""
    out_dir = ART / "sprites" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Every distinct (sheet, frame) this character uses, in first-use order.
    used: list = []
    for _, frames, _, _ in anims:
        for f in frames:
            if f not in used:
                used.append(f)

    # 1. Shared canvas: big enough that every frame fits with its feet on one point.
    #    left/up = the most room any frame needs left of / above its feet, etc.
    metas = {sheet: load_meta(sheet) for sheet, _ in used}
    left = max(m["feet"][0] for m in metas.values())
    up = max(m["feet"][1] for m in metas.values())
    right = max(m["cell_size"][0] - m["feet"][0] for m in metas.values())
    down = max(m["cell_size"][1] - m["feet"][1] for m in metas.values())
    canvas_w, canvas_h = left + right, up + down

    # 2. Paste every frame so its feet land on (left, up).
    padded: dict = {}
    for sheet, index in used:
        meta = metas[sheet]
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        img = Image.open(frame_path(sheet, index)).convert("RGBA")
        canvas.paste(img, (left - meta["feet"][0], up - meta["feet"][1]))
        padded[(sheet, index)] = canvas

    # 2b. Walk/run cycles: line the torsos up. Each frame sits where it was drawn in
    #     its sheet cell, so in a cycle the body slid back and forth a few px per frame
    #     (a stutter-step). Shift each cycle frame sideways so its torso lines up with
    #     the cycle's first frame; the feet then do all the moving, as in a real walk.
    for anim_name, frames, _, loop in anims:
        if not loop or len(set(frames)) < 3:
            continue  # only real cycles (idle and hover are 2-frame breathing loops)
        target = torso_x(padded[frames[0]])
        for key in dict.fromkeys(frames):  # each distinct frame once, in order
            shift = round(target - torso_x(padded[key]))
            if shift:
                moved = Image.new("RGBA", padded[key].size, (0, 0, 0, 0))
                moved.paste(padded[key], (shift, 0))
                padded[key] = moved

    # 3. Trim the empty margin shared by ALL frames (keeps every frame the same
    #    size and the feet on the same pixel, but drops wasted transparent space).
    box = None
    for img in padded.values():
        b = img.getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    feet = [left - box[0], up - box[1]]
    size = [box[2] - box[0], box[3] - box[1]]

    # 4. Write the frames and the SpriteFrames resource.
    ids: dict = {}
    for n, (key, img) in enumerate(padded.items(), start=1):
        sheet, index = key
        file_name = f"{sheet}_{index:02d}.png"
        img.crop(box).save(out_dir / file_name)
        ids[key] = (n, f"res://art/sprites/{name}/{file_name}")

    # Figure height of the first frame (alpha bounding box), used to fit enemies to
    # their hitboxes: sprite scale = hitbox height / figure height.
    first = padded[used[0]].crop(box).getbbox()
    figure_h = first[3] - first[1]

    write_sprite_frames(out_dir / f"{name}_frames.tres", anims, ids)
    meta = {"size": size, "feet": feet, "figure_height": figure_h}
    (out_dir / f"{name}_meta.json").write_text(json.dumps(meta, indent=2))
    # AnimatedSprite2D is centered, so this offset puts the feet on the node origin.
    offset = (size[0] / 2 - feet[0], size[1] / 2 - feet[1])
    print(f"{name:14s} canvas {size[0]}x{size[1]}  feet {feet}  figure_h {figure_h}  offset {offset}")
    return meta


def write_sprite_frames(path: pathlib.Path, anims: list, ids: dict) -> None:
    """Writes a Godot SpriteFrames .tres by hand (it is a plain text format)."""
    lines = [f'[gd_resource type="SpriteFrames" load_steps={len(ids) + 1} format=3]', ""]
    for n, res_path in sorted(ids.values()):
        lines.append(f'[ext_resource type="Texture2D" path="{res_path}" id="{n}"]')
    lines += ["", "[resource]", "animations = ["]
    entries = []
    for anim_name, frames, fps, loop in anims:
        frame_list = ", ".join(
            f'{{"duration": 1.0, "texture": ExtResource("{ids[f][0]}")}}' for f in frames
        )
        entries.append(
            f'{{"frames": [{frame_list}], "loop": {str(loop).lower()}, '
            f'"name": &"{anim_name}", "speed": {fps}}}'
        )
    lines.append(",\n".join(entries))
    lines.append("]")
    path.write_text("\n".join(lines) + "\n")


def build_single(sheet: str, index: int, folder: str, name: str) -> None:
    """Copies one processed frame, trimmed to its visible pixels."""
    out_dir = ART / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(frame_path(sheet, index)).convert("RGBA")
    box = img.getbbox()
    if box is not None:
        img = img.crop(box)
    img.save(out_dir / f"{name}.png")
    print(f"{folder}/{name}.png {img.size[0]}x{img.size[1]}")


def main() -> None:
    """Builds everything: characters, then single sprites, then plain copies.

    `{name: ... for name, anims in CHARACTERS.items()}` is a dict comprehension:
    it loops over the CHARACTERS table and builds a new dict of name -> meta in one line.
    """
    summary = {name: build_character(name, anims) for name, anims in CHARACTERS.items()}
    (ART / "sprites" / "sprites_meta.json").write_text(json.dumps(summary, indent=2))
    for sheet, index, folder, name in SINGLES:
        build_single(sheet, index, folder, name)
    for processed, dest in COPIES:
        target = ART / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(frame_path(processed, 0), target)
        print(f"{dest}")


if __name__ == "__main__":
    main()

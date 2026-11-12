"""tactics_2d/build.py - tactics cell, 2D art: one portrait per unit type, tokens made from it.

The cheap proven style: board-game tokens. A unit needs NO animation at all: one painted
portrait is shown large in the side panel, and the same picture, cropped to the face and put
in a team-coloured ring, is the piece on the board. One image per unit type, no sprite sheets.

    python build.py            # re-runs are free: images are cached in raw/

Pipeline: 3 Nano Banana images -> art_cleanup -> tokens and wall tile made by code -> gate2d
-> demo.tscn (grid_tactics kit) -> screenshot.
"""
import pathlib
import sys

from PIL import Image, ImageDraw, ImageOps

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

# One template, two characters: {who} is filled in with str.format(). Sharing the wording
# is what keeps the two portraits in the same style.
PORTRAIT_PROMPT = (
    "Character portrait for a tactics RPG: {who}. Head and shoulders bust, the face large and "
    "centred in the upper half of the picture, looking slightly to the side, bold painterly "
    "digital illustration with clean shapes and strong rim light, readable at small size. "
    "Original design: no emblems, crests, logos or heraldic symbols anywhere. "
    "Background is one flat solid pure magenta colour (#FF00FF). No text, no frame, no border."
)
UNITS = {
    "knight": ("a stern female knight captain with short silver hair and blue steel armour with gold trim", 0),
    "orc": ("a snarling green orc shaman with small tusks, a bone necklace and a red hood", 1),
}
# Take 2 for the knight: an edit of take 1 that removes the heraldry (see main()).
NO_EMBLEM_PROMPT = (
    "Edit this portrait. Keep the face, hair, pose, lighting and painting style exactly the same. "
    "Remove every emblem, crest, lion head, logo and heraldic symbol from the armour and tabard: "
    "replace them with plain blue steel plates and simple gold edge trim with no symbols at all. "
    "Keep the background one flat solid pure magenta (#FF00FF). No text."
)
FLOOR_PROMPT = (
    "Seamless tileable square floor tile for a tactics board game seen from directly above: warm "
    "grey stone flagstones with thin dark joints and a little moss, painterly, evenly lit, low "
    "contrast so game pieces stand out, the left edge matches the right edge and the top edge "
    "matches the bottom edge. No text."
)
TEAM_RING = {0: (90, 165, 255), 1: (255, 100, 90)}      # blue heroes, red enemies
CELL_PX = 64                                           # board cell size the presenter uses
TOKEN_PX = 56
PANEL_BG = "d8cfb8"            # the parchment panel the big portraits are shown on


def make_token(portrait: Image.Image, team: int) -> Image.Image:
    """Crops the face out of a portrait and puts it in a team-coloured ring.

    The portrait prompt asks for the face in the upper half, so the crop is a fixed square:
    the middle 60 % of the width, starting 6 % from the top. No face detection needed.
    """
    width, height = portrait.size
    side = int(width * 0.6)
    left, top = (width - side) // 2, int(height * 0.06)
    face = portrait.crop((left, top, left + side, top + side)).convert("RGBA")
    # Draw at 4x size and shrink at the end: the cheap way to get smooth circle edges.
    big = TOKEN_PX * 4
    face = face.resize((big, big), Image.LANCZOS)
    disc = Image.new("RGBA", (big, big), (30, 32, 40, 255))        # dark backing for clear pixels
    disc.alpha_composite(face)
    mask = Image.new("L", (big, big), 0)                           # "L" = one channel, 0..255
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    disc.putalpha(mask)
    ring = ImageDraw.Draw(disc)
    ring.ellipse((0, 0, big - 1, big - 1), outline=(20, 20, 26, 255), width=6)
    ring.ellipse((6, 6, big - 7, big - 7), outline=(*TEAM_RING[team], 255), width=18)
    return disc.resize((TOKEN_PX, TOKEN_PX), Image.LANCZOS)


def make_tiles(floor: Image.Image) -> Image.Image:
    """A two-tile atlas for the presenter: the floor at (0,0) and a wall made from it at (1,0).

    The wall is the same stone, darker, with a lighter top edge and a dark bottom edge so it
    reads as a raised block. One generated image gives both tiles.
    """
    floor = floor.convert("RGB").resize((CELL_PX, CELL_PX), Image.LANCZOS)
    wall = floor.point(lambda value: int(value * 0.45))            # point(): apply to every channel value
    draw = ImageDraw.Draw(wall)
    draw.rectangle((0, 0, CELL_PX - 1, CELL_PX - 1), outline=(18, 18, 22), width=2)
    draw.rectangle((2, 2, CELL_PX - 3, 9), fill=(120, 120, 128))    # lit top face
    draw.rectangle((2, CELL_PX - 8, CELL_PX - 3, CELL_PX - 3), fill=(26, 26, 32))
    atlas = Image.new("RGB", (CELL_PX * 2, CELL_PX))
    atlas.paste(floor, (0, 0))
    atlas.paste(wall, (CELL_PX, 0))
    return atlas


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("tactics_2d", "nano-banana portrait -> code-made token", CELL) as log:
        raws = {name: cell_lib.generate(log, CELL, name, PORTRAIT_PROMPT.format(who=who), aspect="1:1")
                for name, (who, _team) in UNITS.items()}         # a dict comprehension: {key: value for ...}
        # Take 1 of the knight came back wearing a lion crest that resembles an existing game
        # franchise's emblem. No gate can see that; it needs a person. Never ship it: re-roll.
        log.reroll("knight: armour carried a lion crest resembling a known franchise emblem")
        log.fail_mode("AI portraits drift toward recognisable franchise designs; say 'no emblems or logos' up front")
        log.add_step("review: rejected knight take 1", cell_lib.GLANCE_SECONDS, human=True)
        raws["knight"] = cell_lib.generate(log, CELL, "knight", NO_EMBLEM_PROMPT, aspect="1:1",
                                           refs=(raws["knight"],), take=2)
        floor_raw = cell_lib.generate(log, CELL, "floor", FLOOR_PROMPT, aspect="1:1")
        if "--generate-only" in sys.argv:
            return
        assets = CELL / "assets"
        (assets / "tokens").mkdir(parents=True, exist_ok=True)
        (assets / "board").mkdir(parents=True, exist_ok=True)
        for name, (_who, team) in UNITS.items():
            cell_lib.cleanup(log, raws[name], assets / "portraits", name, "--single", "--no-snap", "--size", "256x256")
            with log.step(f"token {name}"):
                make_token(Image.open(assets / "portraits" / f"{name}_00.png"), team).save(assets / "tokens" / f"{name}.png")
        cell_lib.looked(log, "two portraits: same style, faces centred so the token crop works")
        with log.step("board tiles"):
            atlas = make_tiles(Image.open(floor_raw))
            atlas.save(assets / "board" / "tiles.png")
        cell_lib.looked(log, "floor tile: calm enough that tokens stand out")
        # The average floor colour is what a token is read against.
        red, green, blue = (sum(channel) // len(channel) for channel in zip(*ImageOps.fit(atlas, (64, 64)).getdata()))
        with log.step("gates"):
            for name in UNITS:
                log.add_gate(gate2d.run_gate(assets / "portraits" / f"{name}_00.png", kind="portrait",
                                             target_height=256, bg=PANEL_BG, godot="off"))
                log.add_gate(gate2d.run_gate(assets / "tokens" / f"{name}.png", kind="portrait", target_height=TOKEN_PX,
                                             bg=f"{red:02x}{green:02x}{blue:02x}", godot="off"))
            log.add_gate(gate2d.run_gate(assets / "board" / "tiles.png", kind="background", godot="off"))
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

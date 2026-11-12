"""fighter_3d/build.py - fighter cell, 3D art: one rigged humanoid, used twice, as a mirror match.

The cheap proven style: every fighter is the SAME rig and clip library, told apart by colour.
The hero is the Quaternius animated base character already fetched for action_rpg_3d (punch,
jab, hit and death clips included), so this cell's only new asset is a floor texture from
Poly Haven. A second fighter costs nothing.

    python build.py            # downloads once, then re-runs offline

Pipeline: shared hero + 1 downloaded texture (shrunk for the web) -> gate3d + gate2d ->
demo.tscn (side-on camera, kit_combat health) -> screenshot.
"""
import pathlib
import sys

from PIL import Image

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

HERO_URL = "https://static.poly.pizza/0b65e14d-a349-44cc-836c-efdeb6933d48.glb"
FLOOR_URL = "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/wood_floor_deck/wood_floor_deck_diff_1k.jpg"
FLOOR_PX = 512           # a floor seen at a shallow angle does not need 1024 px


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("fighter_3d", "one CC rigged humanoid used for both fighters + CC0 floor texture", CELL) as log:
        hero = cell_lib.fetch(log, HERO_URL, cell_lib.SHARED / "quaternius" / "animated_base_character.glb")
        # The full-size download stays out of the repo (runs/ is git-ignored); only the
        # shrunk copy the game uses is kept.
        floor_raw = cell_lib.fetch(log, FLOOR_URL, cell_lib.ART_TESTS / "runs" / "downloads" / "wood_floor_deck_diff_1k.jpg")
        cell_lib.write_credits(CELL, [
            ("animated_base_character.glb", "Quaternius", "poly.pizza/m/cwYvO5UauX", "CC-BY 3.0 (as listed on Poly Pizza)"),
            ("wood_floor_deck (colour map)", "Poly Haven", "polyhaven.com/a/wood_floor_deck", "CC0 1.0"),
        ])
        with log.step("shrink floor texture"):
            # Only the colour map is used. The full PBR set (normal, roughness, ...) is about
            # 2.2 MB at 1K: too much for a web jam build, and unnoticeable under two fighters.
            floor = CELL / "assets" / "floor.jpg"
            floor.parent.mkdir(parents=True, exist_ok=True)
            Image.open(floor_raw).convert("RGB").resize((FLOOR_PX, FLOOR_PX), Image.LANCZOS).save(floor, quality=85)
            Image.open(floor).save(cell_lib.ART_TESTS / "runs" / "fighter_floor.png")       # gate2d reads PNG
        log.note(f"floor texture: {floor_raw.stat().st_size // 1024} KB downloaded, {floor.stat().st_size // 1024} KB shipped")
        cell_lib.looked(log, "floor texture: reads as a deck, no strong pattern under the fighters")
        cell_lib.gate_model(log, hero, kind="character", height=1.8, max_tris=15000,
                            clips=("Rig|Idle_Loop", "Rig|Punch_Jab", "Rig|Punch_Cross", "Rig|Hit_Chest", "Rig|Death01"),
                            loops=("Rig|Idle",),
                            one_shots=("Rig|Punch_Jab", "Rig|Punch_Cross", "Rig|Hit_Chest", "Rig|Death01"))
        with log.step("gate floor"):
            report = gate2d.run_gate(cell_lib.ART_TESTS / "runs" / "fighter_floor.png", kind="background",
                                     budget_kb=600, godot="off")
            log.add_gate({**report, "asset": "floor.jpg"})
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL, frames=100)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

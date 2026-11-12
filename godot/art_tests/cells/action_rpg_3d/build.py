"""action_rpg_3d/build.py - action RPG cell, 3D art: a rigged humanoid with a clip library.

The cheap proven style: low-poly characters that share ONE skeleton and ONE animation
library. The hero here is Quaternius's free animated base character: 45 ready-made clips
(idle, jog, sword attack, roll, hit reactions, death) already on the rig. Nothing is
generated, rigged or animated by us, and no web step (Mixamo, AccuRIG) is needed.

    python build.py            # downloads once, then re-runs offline

Pipeline: download 3 models -> gate3d (file, Blender and Godot layers) -> demo.tscn -> screenshot.
"""
import pathlib
import sys

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog  # noqa: E402

POLY_PIZZA = "https://static.poly.pizza/"
HERO_URL = POLY_PIZZA + "0b65e14d-a349-44cc-836c-efdeb6933d48.glb"
SCENERY = {"rock_medium": POLY_PIZZA + "be5fef3a-4fa1-4d08-b2d4-82e02284588d.glb",
           "plant_big": POLY_PIZZA + "e2b7d78c-f237-4ee8-be1a-62a809097d64.glb"}
# Clip names as they are in the file. Godot strips a trailing "_Loop" on import and makes
# those clips loop, so in the engine "Rig|Idle_Loop" is called "Rig|Idle".
NEEDED_CLIPS = ("Rig|Idle_Loop", "Rig|Jog_Fwd_Loop", "Rig|Sword_Attack", "Rig|Roll", "Rig|Hit_Chest", "Rig|Death01")


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("action_rpg_3d", "CC rigged humanoid + clip library (Quaternius), no manual step", CELL) as log:
        hero = cell_lib.fetch(log, HERO_URL, cell_lib.SHARED / "quaternius" / "animated_base_character.glb")
        scenery = {name: cell_lib.fetch(log, url, CELL / "assets" / f"{name}.glb") for name, url in SCENERY.items()}
        cell_lib.write_credits(CELL, [
            ("animated_base_character.glb", "Quaternius", "poly.pizza/m/cwYvO5UauX", "CC-BY 3.0 (as listed on Poly Pizza)"),
            ("rock_medium.glb", "Quaternius", "poly.pizza/m/s1OJ3bBzqc", "CC0 1.0"),
            ("plant_big.glb", "Quaternius", "poly.pizza/m/MbhbP7JrTI", "CC0 1.0"),
        ])
        cell_lib.looked(log, "picked a character whose clip list covers attack, hit, roll and death")
        log.fail_mode("a clip-library character is a bare mannequin: it gives motion, not identity "
                      "(tinted per team here; a real costume is extra work)")
        log.add_step("search the source site for a rigged, animated character", 600.0, human=True)
        # Loop flags are checked with the names Godot uses AFTER import. one_shots= switches the
        # gate to "clip library" mode: only the clips this game uses are checked, not all 45.
        cell_lib.gate_model(log, hero, kind="character", height=1.8, max_tris=15000, clips=NEEDED_CLIPS,
                            loops=("Rig|Idle", "Rig|Jog_Fwd"),
                            one_shots=("Rig|Sword_Attack", "Rig|Roll", "Rig|Hit_Chest", "Rig|Death01"))
        for name, path in scenery.items():
            cell_lib.gate_model(log, path, kind="environment", budget_kb=1500)
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL, frames=100)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

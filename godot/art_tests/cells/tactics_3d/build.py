"""tactics_3d/build.py - tactics cell, 3D art: static low-poly minis on a textured board.

The cheap proven style: board-game miniatures. A tactics unit does not need a skeleton or a
single animation: it is a small static model on a team-coloured base, and the presenter
slides, flashes and fades it. Any low-poly model works, so the minis here are two unrigged
Kenney models (a hero and a flying drone) and the board is one Poly Haven floor texture.

    python build.py            # downloads once, then re-runs offline

Pipeline: 2 models + 1 texture downloaded -> texture shrunk -> gate3d + gate2d -> demo.tscn
(grid_tactics kit, 3D presenter) -> screenshot.
"""
import pathlib
import sys

from PIL import Image

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

RAW = "https://raw.githubusercontent.com/KenneyNL/"
# Each mini comes from a different kit, and each kit has its OWN Textures/colormap.png, so
# they are kept in separate folders: mixing them would give one mini the wrong colours.
MINIS = {
    "hero": (RAW + "Starter-Kit-3D-Platformer/main/models/", "character.glb"),
    "drone": (RAW + "Starter-Kit-FPS/main/models/", "enemy-flying.glb"),
}
FLOOR_URL = ("https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/concrete_floor_worn_001/"
             "concrete_floor_worn_001_diff_1k.jpg")
FLOOR_PX = 512


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("tactics_3d", "static CC0 kit models as minis (Kenney) + CC0 board texture", CELL) as log:
        models = {}
        for name, (base, file_name) in MINIS.items():        # unpacking: each value is a (base, file) pair
            models[name] = cell_lib.fetch(log, base + file_name, CELL / "assets" / name / file_name)
            cell_lib.fetch(log, base + "Textures/colormap.png", CELL / "assets" / name / "Textures" / "colormap.png")
        floor_raw = cell_lib.fetch(log, FLOOR_URL, cell_lib.ART_TESTS / "runs" / "downloads" / "concrete_floor_worn_001_diff_1k.jpg")
        cell_lib.write_credits(CELL, [
            ("hero/character.glb", "Kenney (kenney.nl)", "github.com/KenneyNL/Starter-Kit-3D-Platformer", "CC0 (models), MIT (repository)"),
            ("drone/enemy-flying.glb", "Kenney (kenney.nl)", "github.com/KenneyNL/Starter-Kit-FPS", "CC0 (models), MIT (repository)"),
            ("concrete_floor_worn_001 (colour map)", "Poly Haven", "polyhaven.com/a/concrete_floor_worn_001", "CC0 1.0"),
        ])
        with log.step("shrink board texture"):
            floor = CELL / "assets" / "board.jpg"
            Image.open(floor_raw).convert("RGB").resize((FLOOR_PX, FLOOR_PX), Image.LANCZOS).save(floor, quality=85)
            Image.open(floor).save(cell_lib.ART_TESTS / "runs" / "tactics_board.png")       # gate2d reads PNG
        cell_lib.looked(log, "two minis read as different units from above; board is calm")
        log.add_step("pick two models and a floor texture", 300.0, human=True)
        # Minis are props: no clips needed, and open shells are fine (nothing gets rigged).
        for name in MINIS:
            # one_shots=() = "clip library" mode with nothing required: the hero model happens to
            # carry walk and idle clips, which a static mini simply ignores.
            cell_lib.gate_model(log, models[name], kind="prop", max_tris=1500, max_non_manifold=None,
                                budget_kb=300, one_shots=())
        with log.step("gate board"):
            report = gate2d.run_gate(cell_lib.ART_TESTS / "runs" / "tactics_board.png", kind="background",
                                     budget_kb=600, godot="off")
            log.add_gate({**report, "asset": "board.jpg"})
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL, frames=120)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

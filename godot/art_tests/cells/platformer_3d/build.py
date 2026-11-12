"""platformer_3d/build.py - platformer cell, 3D art: a Kenney hero on Kenney platforms.

The cheap proven style: one coherent CC0 kit. Kenney's 3D platformer starter kit has a hero
with idle, walk and jump clips plus matching platforms, coins, a flag and clouds, all sharing
one tiny colour-palette texture. Because every piece comes from one author and one palette,
there is nothing to match and almost nothing to gate.

    python build.py            # downloads once, then re-runs offline

Pipeline: download 8 small models -> gate3d -> demo.tscn -> screenshot.
"""
import pathlib
import sys

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog  # noqa: E402

KIT = "https://raw.githubusercontent.com/KenneyNL/Starter-Kit-3D-Platformer/main/models/"
PIECES = ("character", "platform", "platform-medium", "platform-grass-large-round", "coin", "flag", "cloud", "brick")


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("platformer_3d", "one CC0 kit (Kenney): hero with clips + matching platforms", CELL) as log:
        models = {name: cell_lib.fetch(log, KIT + name + ".glb", CELL / "assets" / f"{name}.glb") for name in PIECES}
        # The kit's models do not contain their texture: they all point at one shared file,
        # Textures/colormap.png, next to them. Forget it and everything imports plain white
        # (the godot_import gate fails with "Can't open file ... colormap.png").
        cell_lib.fetch(log, KIT + "Textures/colormap.png", CELL / "assets" / "Textures" / "colormap.png")
        log.fail_mode("kit models reference an external shared texture: copy the Textures folder with them")
        cell_lib.write_credits(CELL, [
            (", ".join(f"{name}.glb" for name in PIECES), "Kenney (kenney.nl)",
             "github.com/KenneyNL/Starter-Kit-3D-Platformer", "CC0 (models), MIT (repository)"),
        ])
        cell_lib.looked(log, "kit pieces: one style, hero has idle / walk / jump")
        log.add_step("find the kit and pick the pieces", 300.0, human=True)
        # The hero is animated by moving whole parts (no skeleton), so the bone gates skip.
        # The gate is told which clips the game needs looping (idle, walk) and which must
        # play once (jump); the kit's file already marks them correctly.
        # max_non_manifold=None: the hero is built from open shells (34 open edges). That only
        # matters for auto-rigging, and this hero is never rigged.
        cell_lib.gate_model(log, models["character"], kind="prop", max_tris=3000, max_non_manifold=None,
                                   clips=("idle", "walk", "jump"), loops=("idle", "walk"), one_shots=("jump",))
        for name in ("platform-medium", "platform-grass-large-round", "coin"):
            cell_lib.gate_model(log, models[name], kind="environment", budget_kb=300)
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

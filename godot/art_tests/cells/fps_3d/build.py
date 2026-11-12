"""fps_3d/build.py - FPS cell, 3D art: a kit-built arena, a pipeline-built enemy, and fog.

The cheap proven style: low-poly, flat colours, heavy fog. Two sources:
  level   Kenney's CC0 FPS starter kit (walls, floor slabs, a blaster): downloaded
  enemy   a low-poly boar made by this repo's own pipeline3d (forge.py): a Blender script
          builds the body, auto-rigs it and adds four clips. No AI, no key, no download.

    python build.py            # downloads once and forges once; re-runs reuse both

Pipeline: forge the boar + download 5 kit models -> gate3d -> demo.tscn (fps_kit) -> screenshot.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog  # noqa: E402

KIT = "https://raw.githubusercontent.com/KenneyNL/Starter-Kit-FPS/main/models/"
PIECES = ("wall-high", "wall-low", "platform", "platform-large-grass", "blaster")
FORGE = cell_lib.REPO / "pipeline3d" / "forge.py"
BOAR_CLIPS = ("boar_idle", "boar_walk", "boar_attack", "boar_death")


def forge_boar(log: RunLog) -> pathlib.Path:
    """Runs pipeline3d on boar.json and copies the finished model into assets/. Skips if present."""
    boar = CELL / "assets" / "boar.glb"
    if boar.is_file():
        log.add_step("forge boar (already built: 13 s when it runs)", 13.0)
        return boar
    # forge.py puts its work folder next to the manifest unless the manifest says where.
    # A copy of boar.json with "workdir" pointing into runs/ (git-ignored, hidden from Godot)
    # keeps the half-built files out of the Godot project.
    work = cell_lib.ART_TESTS / "runs" / "forge"
    work.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CELL / "boar.json").read_text(encoding="utf-8"))
    manifest["workdir"] = str(work / "boar")
    (work / "boar.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with log.step("forge boar (generate, rig, animate, export, audit)"):
        run = subprocess.run([sys.executable, str(FORGE), str(work / "boar.json")],
                             capture_output=True, text=True, timeout=900, env=os.environ)
    if run.returncode != 0:
        log.fail_mode("forge.py failed: " + run.stdout.strip()[-200:])
        raise RuntimeError(run.stdout[-600:])
    boar.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(work / "boar" / "export" / "boar.glb", boar)
    return boar


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("fps_3d", "CC0 kit level (Kenney) + pipeline3d procedural rigged enemy + fog", CELL) as log:
        boar = forge_boar(log)
        models = {name: cell_lib.fetch(log, KIT + name + ".glb", CELL / "assets" / f"{name}.glb") for name in PIECES}
        # Same rule as the platformer kit: the models point at a shared texture next to them.
        cell_lib.fetch(log, KIT + "Textures/colormap.png", CELL / "assets" / "Textures" / "colormap.png")
        cell_lib.write_credits(CELL, [
            (", ".join(f"{name}.glb" for name in PIECES), "Kenney (kenney.nl)",
             "github.com/KenneyNL/Starter-Kit-FPS", "CC0 (models), MIT (repository)"),
            ("boar.glb", "made here by pipeline3d/forge.py from boar.json", "this repository", "yours"),
        ])
        cell_lib.looked(log, "boar turnaround: reads as a boar, legs bend the right way")
        cell_lib.looked(log, "kit pieces: walls and floor share a style")
        log.fail_mode("a kit's palette sets the mood: this pastel kit fights a horror tone (fog and dim light only go so far)")
        log.fail_mode("kit props are not sized for first-person use: the blaster is 1.6 m long and needed scaling to 0.2")
        log.add_step("find the kit and pick the pieces", 300.0, human=True)
        cell_lib.gate_model(log, boar, kind="prop", height=0.9, max_tris=1500, clips=BOAR_CLIPS,
                            loops=("boar_idle", "boar_walk"), one_shots=("boar_attack", "boar_death"),
                            min_retention=0.5)
        for name in ("wall-high", "platform-large-grass"):
            cell_lib.gate_model(log, models[name], kind="environment", budget_kb=300)
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

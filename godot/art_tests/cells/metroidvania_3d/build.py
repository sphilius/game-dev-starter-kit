"""metroidvania_3d/build.py - metroidvania cell, 3D art shown from the side ("2.5D").

The cheap proven style: 3D models, 2D gameplay. The camera looks straight at the side of the
level, so platforms are plain boxes with one rock texture, depth comes from fog and a few
coloured lights, and the hero needs only a run clip seen from one angle.
Hero: the Khronos sample Fox (rigged, with Survey / Walk / Run). Rock: ambientCG Rock030.

    python build.py            # downloads once, then re-runs offline

Pipeline: 1 model + 1 texture set downloaded -> texture shrunk -> gate3d + gate2d ->
demo.tscn -> screenshot.
"""
import pathlib
import sys
import zipfile

from PIL import Image

CELL = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(CELL.parent))
import cell_lib  # noqa: E402
from cell_lib import RunLog, gate2d  # noqa: E402

FOX_URL = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/Fox/glTF-Binary/Fox.glb"
ROCK_URL = "https://ambientcg.com/get?file=Rock030_1K-JPG.zip"
ROCK_PX = 512


def main() -> None:
    """Runs the whole cell and writes report.json next to this file."""
    with RunLog("metroidvania_3d", "CC rigged animal (Khronos Fox) + CC0 rock texture on boxes, side camera", CELL) as log:
        fox = cell_lib.fetch(log, FOX_URL, CELL / "assets" / "fox.glb")
        rock_zip = cell_lib.fetch(log, ROCK_URL, cell_lib.ART_TESTS / "runs" / "downloads" / "Rock030_1K-JPG.zip")
        cell_lib.write_credits(CELL, [
            ("fox.glb", "PixelMannen (model), tomkranis (rig and animation), AsoboStudio and scurest (glTF conversion)",
             "github.com/KhronosGroup/glTF-Sample-Assets, Models/Fox", "CC0 1.0 (model), CC-BY 4.0 (rig, animation, conversion)"),
            ("Rock030 (colour map)", "ambientCG", "ambientcg.com/a/Rock030", "CC0 1.0"),
        ])
        with log.step("extract and shrink rock texture"):
            # The zip holds a full PBR set (colour, normal, roughness, displacement...): 9.7 MB.
            # Only the colour map is taken, at 512 px: fog and coloured lights do the rest.
            rock = CELL / "assets" / "rock.jpg"
            with zipfile.ZipFile(rock_zip) as archive:        # "with" closes the zip when the block ends
                colour_name = next(name for name in archive.namelist() if name.endswith("_Color.jpg"))
                with archive.open(colour_name) as member:
                    Image.open(member).convert("RGB").resize((ROCK_PX, ROCK_PX), Image.LANCZOS).save(rock, quality=85)
            Image.open(rock).save(cell_lib.ART_TESTS / "runs" / "metroidvania_rock.png")      # gate2d reads PNG
        log.note(f"rock texture: {rock_zip.stat().st_size // 1024} KB downloaded, {rock.stat().st_size // 1024} KB shipped")
        cell_lib.looked(log, "fox has a run clip; rock texture is neutral enough to tint with lights")
        log.add_step("find a rigged, animated model and a rock texture on the two sites", 420.0, human=True)
        # No height is asked for: the gate reports the size it finds, which is the point here.
        report = cell_lib.gate_model(log, fox, kind="prop", clips=("Run", "Walk", "Survey"),
                                     loops=("Run", "Walk"), one_shots=())
        size_check = next(c for c in report["checks"] if c["name"] == "height")
        if size_check["value"] and size_check["value"] > 10:
            # The fox is modelled in centimetres: 75 "metres" tall. Scaled by 0.01 in the scene.
            log.fail_mode(f"downloaded model is not in metres ({size_check['value']:.0f} units tall): scale it in the scene")
        with log.step("gate rock"):
            rock_report = gate2d.run_gate(cell_lib.ART_TESTS / "runs" / "metroidvania_rock.png", kind="background",
                                          budget_kb=600, godot="off")
            log.add_gate({**rock_report, "asset": "rock.jpg"})
        if "--no-demo" not in sys.argv:
            cell_lib.godot_import(log)
            cell_lib.screenshot(log, CELL)
    print("gates passed:", log.summary()["gates_passed"], "| failed:", log.summary()["gates_failed"])


if __name__ == "__main__":
    main()

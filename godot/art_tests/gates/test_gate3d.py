"""test_gate3d.py - proves each 3D gate catches the defect it is named after.

    BLENDER=/path/to/blender GODOT=/path/to/godot_console python test_gate3d.py

Needs Blender to build its test models (it runs pipeline3d's own stage test, which makes a
rigged wolf with four clips, a crate, a humanoid and a knife from code: no downloaded or
AI-made files). Without BLENDER it prints SKIP and exits 0, so CI without Blender stays green.
Same method as test_gate2d.py: a good model passes, then one thing at a time is made wrong.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gate3d  # noqa: E402
import glb_facts  # noqa: E402

PIPELINE3D = pathlib.Path(__file__).resolve().parents[3] / "pipeline3d"
WOLF_CLIPS = ("idle", "walk", "wolf_attack", "wolf_death")
# Fast options: skip Blender and Godot unless a test is about that layer.
FILE_ONLY = {"blender": "off", "godot": "off"}


def check(condition: bool, message: str) -> None:
    """Stops the test with a clear message when a check fails."""
    if not condition:
        sys.exit(f"FAIL: {message}")


def verdict(report: dict, name: str) -> bool | None:
    """The pass/fail/skip result of one named gate in a report."""
    return next(c["passed"] for c in report["checks"] if c["name"] == name)


def build_fixtures(blender: str, out: pathlib.Path) -> pathlib.Path:
    """Runs pipeline3d's stage test to make the models; returns the folder holding the .glb files."""
    run = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "1",
                          "-P", str(PIPELINE3D / "tests" / "test_blender_stages.py"), "--", f"out_dir={out}"],
                         capture_output=True, text=True, timeout=600)
    check(run.returncode == 0, "pipeline3d fixtures failed to build:\n" + "\n".join(run.stdout.splitlines()[-5:]))
    return out / "export"


def build_open_plane(blender: str, path: pathlib.Path) -> None:
    """Makes a single flat square: its four outer edges each touch only one face (non-manifold)."""
    script = ("import bpy\n"
              "[bpy.data.objects.remove(o) for o in list(bpy.data.objects)]\n"
              "bpy.ops.mesh.primitive_plane_add(size=1)\n"
              f"bpy.ops.export_scene.gltf(filepath=r'{path}', export_format='GLB')\n")
    run = subprocess.run([blender, "-b", "--factory-startup", "--python-expr", script], capture_output=True, text=True, timeout=300)
    check(path.is_file(), "could not build the open-plane model:\n" + run.stdout[-400:])


def test_facts(models: pathlib.Path) -> None:
    """glb_facts reads the numbers pipeline3d's own tests promise for these models."""
    wolf = glb_facts.facts(models / "wolf_merged.glb")
    check(wolf["bones"] == 39 and wolf["max_influences"] == 4, f"wolf rig facts wrong: {wolf}")
    check(sorted(c["name"] for c in wolf["clips"]) == sorted(WOLF_CLIPS), f"wolf clips wrong: {wolf['clips']}")
    human = glb_facts.facts(models / "character.glb")
    check(abs(human["size"][1] - 1.78) < 0.01, f"humanoid should be 1.78 m tall on Y: {human['size']}")
    check(abs(human["bounds_min"][1]) < 0.01, f"humanoid feet should be at y = 0: {human['bounds_min']}")


def test_file_gates(models: pathlib.Path) -> None:
    """Each file-level gate fails when its one input is wrong (and passes when it is right)."""
    human = models / "character.glb"
    good = gate3d.run_gate(human, kind="character", height=1.78, **FILE_ONLY)
    check(good["passed"], f"a correct humanoid should pass the file gates: {good['failed']}")
    check(verdict(good, "non_manifold") is None and verdict(good, "godot_import") is None,
          "with both tools off, the Blender and Godot gates must be skipped, not failed")

    check(gate3d.run_gate(human, kind="character", max_tris=100, **FILE_ONLY)["failed"] == ["tri_budget"],
          "a 100-triangle budget should fail tri_budget only")
    check(gate3d.run_gate(human, kind="character", height=3.0, **FILE_ONLY)["failed"] == ["height"],
          "a wrong expected height should fail height only")
    # The wolf is long (Z) rather than tall (Y): as a "character" it must trip the up-axis gate.
    check("y_up" in gate3d.run_gate(models / "wolf_merged.glb", kind="character", **FILE_ONLY)["failed"],
          "a model whose longest axis is not Y should fail y_up as a character")
    # The knife's origin is at its ring, so the blade hangs 15 cm below y = 0.
    check("origin" in gate3d.run_gate(models / "karambit.glb", kind="prop", **FILE_ONLY)["failed"],
          "a model that extends below the ground should fail origin")
    missing = gate3d.run_gate(models / "wolf_merged.glb", kind="prop", clips=("idle", "jump"), **FILE_ONLY)
    check(missing["failed"] == ["clip_names"], f"a missing clip should fail clip_names only: {missing['failed']}")
    check(gate3d.run_gate(models / "wolf_merged.glb", kind="prop", max_bones=20, **FILE_ONLY)["failed"] == ["bones"],
          "39 bones against a limit of 20 should fail bones only")


def test_blender_gates(models: pathlib.Path, tmp: pathlib.Path) -> None:
    """Blender layer: watertight models pass, an open plane fails for props but not for scenery."""
    renders = tmp / "renders"
    wolf = gate3d.run_gate(models / "wolf_merged.glb", kind="prop", render_dir=renders, godot="off")
    check(verdict(wolf, "non_manifold") is True, "the wolf is watertight")
    check(verdict(wolf, "bend") is True, f"the wolf's joints should hold: {wolf['checks']}")
    check(verdict(wolf, "turnaround") is True and len(list(renders.glob("*.png"))) >= 4, "four turnaround renders")
    strict = gate3d.run_gate(models / "wolf_merged.glb", kind="prop", min_retention=0.95, godot="off")
    check("bend" in strict["failed"], "an impossible 0.95 retention bar should fail bend")

    plane = tmp / "plane.glb"
    build_open_plane(os.environ["BLENDER"], plane)
    as_prop = gate3d.run_gate(plane, kind="prop", godot="off")
    check("non_manifold" in as_prop["failed"], f"an open plane should fail non_manifold as a prop: {as_prop['checks']}")
    check(verdict(as_prop, "bend") is None, "an unrigged model skips the bend gate")
    as_scenery = gate3d.run_gate(plane, kind="environment", godot="off")
    check(verdict(as_scenery, "non_manifold") is None, "open edges are only reported for environment pieces")


def test_godot_gates(models: pathlib.Path) -> None:
    """Godot layer: clean import, loop flags checked against what was asked, size budget enforced."""
    wolf = models / "wolf_merged.glb"
    good = gate3d.run_gate(wolf, kind="prop", clips=WOLF_CLIPS, loops=("idle", "walk"), blender="off")
    check(good["passed"], f"the wolf should pass the Godot gates: {good['failed']} {good['checks'][-3:]}")
    wrong_loops = gate3d.run_gate(wolf, kind="prop", loops=("idle",), blender="off")
    check(wrong_loops["failed"] == ["clip_loops"], f"walk loops but was not asked to: {wrong_loops['failed']}")
    tight = gate3d.run_gate(wolf, kind="prop", loops=("idle", "walk"), budget_kb=1.0, blender="off")
    check(tight["failed"] == ["web_size"], f"a 1 KB budget should fail web_size only: {tight['failed']}")


if __name__ == "__main__":
    if not gate3d.find_tool(None, "BLENDER"):
        print("SKIP: set BLENDER to run the 3D gate tests")
        sys.exit(0)
    with tempfile.TemporaryDirectory() as folder:
        tmp = pathlib.Path(folder)
        models = build_fixtures(os.environ["BLENDER"], tmp / "fixtures")
        test_facts(models)
        test_file_gates(models)
        test_blender_gates(models, tmp)
        if gate3d.find_tool(None, "GODOT"):
            test_godot_gates(models)
        else:
            print("  Godot gates skipped (set GODOT to run them)")
    print("PASS")

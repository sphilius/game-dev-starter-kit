"""test_gate2d.py - proves each 2D gate catches the defect it is named after.

Run it and it prints PASS, or stops at the first failed check with a message:
    python test_gate2d.py
    GODOT=/path/to/godot_console.exe python test_gate2d.py     (also runs the import gate)

Method: build clean frames with art_cleanup.py from the synthetic sheet in
test_art_cleanup.py (Medusa's raw art is not in any repo), confirm every gate passes, then
break ONE thing at a time and confirm exactly that gate fails. A gate that cannot fail is
worthless, so the failing cases matter more than the passing one.
"""
import pathlib
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import art_cleanup  # noqa: E402
import gate2d  # noqa: E402
import test_art_cleanup  # noqa: E402  (for its synthetic sheet generator)

# Gate options matching the synthetic sheet: vase palette, shown 64 px tall on a pale wall.
# godot="off": starting Godot costs ~7 s, so only test_godot_import_gate runs the import gate.
OPTIONS = {"palette": "vase", "target_height": 64, "bg": "e2a27a", "godot": "off"}


def check(condition: bool, message: str) -> None:
    """Stops the test with a clear message when a check fails."""
    if not condition:
        sys.exit(f"FAIL: {message}")


def failed(report: dict) -> list[str]:
    """The names of the gates that failed in a report."""
    return report["failed"]


def clean_frames(tmp: pathlib.Path) -> pathlib.Path:
    """Makes the synthetic sheet, cleans it, and returns the folder of frame PNGs."""
    raw = tmp / "sheet.png"
    test_art_cleanup.make_sheet(raw)
    out = tmp / "clean"
    art_cleanup.main([str(raw), "--name", "hero", "--out", str(out), "--fit-height", "128"])
    return out


def variant(clean: pathlib.Path, name: str) -> pathlib.Path:
    """A fresh copy of the clean frames to break in one specific way."""
    target = clean.parent / name
    shutil.copytree(clean, target)
    return target


def edit_frame(folder: pathlib.Path, index: int, change) -> None:
    """Loads frame `index`, passes its pixel array to `change` (a function), saves the result.

    Passing a function as an argument lets each test say only WHAT to change.
    """
    path = folder / f"hero_{index:02d}.png"
    rgba = np.array(Image.open(path).convert("RGBA"))
    Image.fromarray(change(rgba)).save(path)


def test_clean_frames_pass(clean: pathlib.Path) -> None:
    """Good art passes every gate that ran."""
    report = gate2d.run_gate(clean, **OPTIONS)      # ** unpacks the dict into keyword arguments
    check(report["passed"], f"clean frames should pass, failed: {failed(report)} {report['checks']}")
    check(report["frames"] == 6, f"expected 6 frames, gate saw {report['frames']}")
    names = [c["name"] for c in report["checks"]]
    check(names == ["alpha_fringe", "palette", "frame_size", "feet_baseline", "silhouette_iou",
                    "readability", "texture_budget", "godot_import"], f"gate list changed: {names}")


def test_fringe_is_caught(clean: pathlib.Path) -> None:
    """A magenta halo left around the shape (the classic bad key) fails alpha_fringe only."""
    folder = variant(clean, "fringe")

    # A nested function: defined inside the test because only this test needs it.
    def add_halo(rgba: np.ndarray) -> np.ndarray:
        """Paints a one-pixel magenta ring around the shape."""
        solid = rgba[..., 3] > 0
        grown = np.zeros_like(solid)
        grown[1:, :] |= solid[:-1, :]               # shift the shape one pixel each way...
        grown[:-1, :] |= solid[1:, :]
        grown[:, 1:] |= solid[:, :-1]
        grown[:, :-1] |= solid[:, 1:]
        halo = grown & ~solid                       # ...and keep only the new ring
        rgba[halo] = (255, 0, 255, 255)
        return rgba

    for i in range(6):
        edit_frame(folder, i, add_halo)
    report = gate2d.run_gate(folder, **OPTIONS)
    check("alpha_fringe" in failed(report), f"magenta halo not caught: {failed(report)}")


def test_off_palette_is_caught(clean: pathlib.Path) -> None:
    """Colour drift (here: everything shifted toward blue) fails the palette gate."""
    folder = variant(clean, "drift")

    def tint(rgba: np.ndarray) -> np.ndarray:
        """Adds 60 to the blue channel of every pixel."""
        rgba[..., 2] = np.clip(rgba[..., 2].astype(int) + 60, 0, 255)
        return rgba

    edit_frame(folder, 2, tint)
    report = gate2d.run_gate(folder, **OPTIONS)
    check(failed(report) == ["palette"], f"expected only the palette gate to fail, got {failed(report)}")


def test_mixed_frame_sizes_are_caught(clean: pathlib.Path) -> None:
    """One frame saved at a different size fails frame_size."""
    folder = variant(clean, "sizes")
    edit_frame(folder, 1, lambda rgba: rgba[:-10, :, :])     # lambda: a one-line unnamed function
    report = gate2d.run_gate(folder, **OPTIONS)
    check("frame_size" in failed(report), f"mixed sizes not caught: {failed(report)}")


def test_baseline_drift_is_caught(clean: pathlib.Path) -> None:
    """A frame floating 8 px above the ground fails feet_baseline, unless it is marked airborne."""
    folder = variant(clean, "bob")

    def lift(rgba: np.ndarray) -> np.ndarray:
        """Moves the whole picture up 8 pixels."""
        lifted = np.zeros_like(rgba)
        lifted[:-8] = rgba[8:]
        return lifted

    edit_frame(folder, 3, lift)
    report = gate2d.run_gate(folder, **OPTIONS)
    check("feet_baseline" in failed(report), f"8 px bob not caught: {failed(report)}")
    report = gate2d.run_gate(folder, airborne=(3,), **OPTIONS)
    check("feet_baseline" not in failed(report), "an airborne (jump) frame should be exempt")


def test_popping_frame_is_caught(clean: pathlib.Path) -> None:
    """A frame whose shape barely overlaps its neighbours (a pose from another character) fails IoU."""
    folder = variant(clean, "pop")

    def replace_with_bar(rgba: np.ndarray) -> np.ndarray:
        """Throws the pose away and draws a low bar instead."""
        out = np.zeros_like(rgba)
        out[-12:, :, :] = (0x1A, 0x14, 0x10, 255)   # a flat bar on the ground: same feet, wrong shape
        return out

    edit_frame(folder, 4, replace_with_bar)
    report = gate2d.run_gate(folder, **OPTIONS)
    check("silhouette_iou" in failed(report), f"popping frame not caught: {failed(report)}")


def test_unreadable_art_is_caught(clean: pathlib.Path) -> None:
    """Too small on screen, or the same colour as the background, fails readability."""
    tiny = gate2d.run_gate(clean, palette="vase", target_height=10, bg="e2a27a", godot="off")
    check("readability" in failed(tiny), f"10 px tall figure should be unreadable: {failed(tiny)}")
    camouflaged = gate2d.run_gate(clean, palette="vase", target_height=64, bg="1a1410", godot="off")
    check("readability" in failed(camouflaged), f"black figure on a black level not caught: {failed(camouflaged)}")


def test_budget_is_enforced(clean: pathlib.Path) -> None:
    """A budget smaller than the files fails texture_budget (the value reports the real size)."""
    report = gate2d.run_gate(clean, budget_kb=1.0, **OPTIONS)
    check("texture_budget" in failed(report), f"1 KB budget should fail: {failed(report)}")


def test_kind_switches_animation_gates(clean: pathlib.Path) -> None:
    """Portraits, tilesets and backgrounds skip the two animation gates."""
    report = gate2d.run_gate(clean, kind="portrait", **OPTIONS)
    names = [c["name"] for c in report["checks"]]
    check("feet_baseline" not in names and "silhouette_iou" not in names, f"portrait ran animation gates: {names}")


def test_godot_import_gate(clean: pathlib.Path) -> None:
    """With a Godot exe available the import gate must run and pass; without one it is skipped."""
    report = gate2d.run_gate(clean, palette="vase", target_height=64, bg="e2a27a")   # no godot="off" here
    result = next(c for c in report["checks"] if c["name"] == "godot_import")    # first matching item
    import os
    if os.environ.get("GODOT"):
        check(result["passed"] is True, f"clean frames should import without warnings: {result}")
    else:
        check(result["passed"] is None, f"without GODOT the import gate should be skipped: {result}")
    print(f"  godot_import: {'ran' if result['passed'] is not None else 'skipped (set GODOT to run it)'}")


def report_medusa_baseline() -> None:
    """Not a test: prints the gate numbers for Medusa's shipped sheets as the baseline to beat.

    Looks for a medusas-price checkout next to this repo; silently skips when it is absent (CI).
    """
    processed = pathlib.Path(__file__).resolve().parents[4] / "medusas-price" / "art" / "processed"
    for name, extra in [("medusa_a", {"airborne": (6, 7)}), ("enemy_hoplites", {})]:
        folder = processed / name
        if not folder.is_dir():
            continue
        report = gate2d.run_gate(folder, palette="vase", target_height=64, bg="e2a27a", godot="off", **extra)
        summary = ", ".join(f"{c['name']}={c['value']}" for c in report["checks"] if c["passed"] is not None)
        print(f"  baseline {name}: {'PASSED' if report['passed'] else 'FAILED ' + str(report['failed'])}  {summary}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        clean = clean_frames(pathlib.Path(folder))
        test_clean_frames_pass(clean)
        test_fringe_is_caught(clean)
        test_off_palette_is_caught(clean)
        test_mixed_frame_sizes_are_caught(clean)
        test_baseline_drift_is_caught(clean)
        test_popping_frame_is_caught(clean)
        test_unreadable_art_is_caught(clean)
        test_budget_is_enforced(clean)
        test_kind_switches_animation_gates(clean)
        test_godot_import_gate(clean)
    report_medusa_baseline()
    print("PASS")

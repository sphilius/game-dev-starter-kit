"""cell_lib.py - the steps every cell of the art-test matrix shares.

A "cell" is one genre in one dimension (fps_2d, tactics_3d ...). Each cell folder has a
build.py that calls these helpers in order:

    generate()    one paid Nano Banana image (cached, so a re-run never pays twice)
    cleanup()     raw image -> keyed, sliced, aligned frames (gates/art_cleanup.py)
    gate 2D/3D    gates/gate2d.py or gates/gate3d.py, attached to the run log
    screenshot()  the cell's demo scene rendered by Godot (tools/capture.gd)

Everything is timed and costed through gates/runlog.py, which writes the cell's report.json.
Dev-only: nothing here ships in a game.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

ART_TESTS = pathlib.Path(__file__).resolve().parent.parent          # godot/art_tests
GODOT_PROJECT = ART_TESTS.parent                                    # godot/
REPO = GODOT_PROJECT.parent
BANANA = REPO / ".agents" / "skills" / "nano-banana" / "scripts" / "banana.py"
sys.path.insert(0, str(ART_TESTS / "gates"))
import art_cleanup  # noqa: E402  (imported after the path line above on purpose)
import gate2d  # noqa: E402
import gate3d  # noqa: E402
from runlog import RunLog  # noqa: E402,F401  (re-exported so build.py needs one import)

# Estimated dollars per 1K image. Google bills by output tokens, so these are estimates.
# Calibrated on 2026-11-12: Cloud Billing charged $0.73 for the 21 lite images that had been
# estimated at $0.02 each, i.e. about $0.035 per image. The other models were scaled by the
# same factor (x1.75); they have not been checked against a bill yet.
PRICE_USD = {"nano-banana-2-lite": 0.035, "nano-banana": 0.07, "nano-banana-2": 0.12, "nano-banana-pro": 0.25}
# Seconds a person needs to look at one image and say yes or no. An estimate, used for
# every approval so cells compare fairly; your own number may differ.
GLANCE_SECONDS = 20.0


def api_key() -> str:
    """The Gemini key from the environment, or from the Windows *user* variables. Never printed."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key and sys.platform == "win32":
        # A variable set with "setx" is invisible to shells that were already open; ask Windows.
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
            key = winreg.QueryValueEx(env, "GEMINI_API_KEY")[0]
    return key


def generate(log: RunLog, cell_dir: pathlib.Path, name: str, prompt: str, *, aspect: str = "1:1",
             model: str = "nano-banana-2-lite", refs: tuple = (), take: int = 1) -> pathlib.Path:
    """Makes one image with Nano Banana and returns the raw PNG path.

    The image and a small .json receipt (prompt, seconds, cost) are kept in <cell>/raw/.
    If both already exist, nothing is generated and nothing is spent: the receipt's time
    and cost are copied into this run's report instead. Raise `take` to pay for a re-roll.
    """
    raw = cell_dir / "raw" / f"{name}_t{take}.png"
    receipt = raw.with_suffix(".json")
    if raw.is_file() and receipt.is_file():
        info = json.loads(receipt.read_text(encoding="utf-8"))
        log.add_step(f"generate {name} take {take} (cached)", info["wall_s"])
        log.spends.append(info["spend"])        # report only: the ledger already has this row
        return raw
    cost = PRICE_USD[model]
    if not log.can_spend(cost):
        raise RuntimeError(f"budget cap reached, not generating {name}")
    raw.parent.mkdir(parents=True, exist_ok=True)
    command = ["uv", "run", str(BANANA), "-p", prompt, "-f", str(raw), "-r", "1K", "-a", aspect, "-m", model]
    for ref in refs:                             # reference images keep a character on-model
        command += ["-i", str(ref)]
    started = time.perf_counter()
    # {**a, "K": v} copies the environment and adds one entry, without changing our own.
    run = subprocess.run(command, capture_output=True, text=True, env={**os.environ, "GEMINI_API_KEY": api_key()})
    seconds = round(time.perf_counter() - started, 1)
    if run.returncode != 0 or not raw.is_file():
        log.fail_mode(f"generate {name} failed: {run.stderr.strip()[-200:]}")
        raise RuntimeError(f"banana.py failed for {name}: {run.stderr.strip()[-400:]}")
    log.add_step(f"generate {name} take {take}", seconds)
    log.spend(cost, "gemini-api", model, images=1, resolution="1K", wall_s=seconds, purpose=name)
    receipt.write_text(json.dumps({"prompt": prompt, "model": model, "aspect": aspect, "wall_s": seconds,
                                   "refs": [pathlib.Path(r).name for r in refs],
                                   "spend": log.spends[-1]}, indent=2) + "\n", encoding="utf-8")
    return raw


def cleanup(log: RunLog, raw: pathlib.Path, out_dir: pathlib.Path, name: str, *options: str) -> dict:
    """Runs art_cleanup on a raw image. `options` are its command-line flags, e.g. "--fit-height", "96"."""
    with log.step(f"cleanup {name}"):
        return art_cleanup.main([str(raw), "--name", name, "--out", str(out_dir), *options])


def looked(log: RunLog, note: str) -> None:
    """Records one human glance at an output: an approval plus the standard glance time."""
    log.approve(note)
    log.add_step(f"review: {note}", GLANCE_SECONDS, human=True)


def find_tools() -> None:
    """Fills in GODOT and BLENDER from their usual Windows install folders when they are not set.

    Shell variables do not survive between terminal sessions, so a jam-day run should not
    depend on remembering to export them. A value already in the environment always wins.
    """
    local = pathlib.Path(os.environ.get("LOCALAPPDATA", ""))
    guesses = {
        # sorted(...)[-1:] keeps the last match (the newest version) or an empty list.
        "GODOT": sorted(local.glob("Microsoft/WinGet/Packages/GodotEngine.GodotEngine_*/Godot_v4*_win64_console.exe"))[-1:],
        "BLENDER": sorted(pathlib.Path("C:/Program Files/Blender Foundation").glob("Blender */blender.exe"))[-1:],
    }
    for name, found in guesses.items():
        if not os.environ.get(name) and found:
            os.environ[name] = str(found[0])


find_tools()


def godot_exe() -> str:
    """The Godot console executable (GODOT variable, or the install found by find_tools)."""
    exe = os.environ.get("GODOT", "")
    if not exe:
        sys.exit("set GODOT to the Godot 4.7.2 console executable (see art_tests/ENV.md)")
    return exe


def godot_import(log: RunLog) -> None:
    """Has Godot import new files (textures, models, scripts) so the demo scene can load them."""
    with log.step("godot import"):
        subprocess.run([godot_exe(), "--headless", "--path", str(GODOT_PROJECT), "--import"],
                       capture_output=True, text=True, timeout=600)


def screenshot(log: RunLog, cell_dir: pathlib.Path, scene: str = "demo.tscn", frames: int = 90) -> pathlib.Path:
    """Renders the cell's demo scene in a short-lived window and saves <cell>/screenshot.png."""
    out = cell_dir / "screenshot.png"
    res_scene = "res://" + (cell_dir / scene).relative_to(GODOT_PROJECT).as_posix()
    with log.step("screenshot"):
        run = subprocess.run([godot_exe(), "--path", str(GODOT_PROJECT), "--script", "res://art_tests/tools/capture.gd",
                              "--", f"--scene={res_scene}", f"--out={out.as_posix()}", f"--frames={frames}"],
                             capture_output=True, text=True, timeout=300)
    # Any script error in the demo is a failed cell, even if a picture was saved.
    errors = [line for line in (run.stdout + run.stderr).splitlines() if "ERROR" in line or "SCRIPT ERROR" in line]
    if run.returncode != 0 or errors or not out.is_file():
        log.fail_mode("demo scene errors: " + " | ".join(errors[:3]))
        raise RuntimeError("screenshot failed:\n" + "\n".join(errors[:8] or [run.stdout[-400:]]))
    return out


# ---- 3D cells: downloaded CC0 / CC-BY assets ------------------------------------------------

# Where models shared by several cells are kept (one copy in the repo, not one per cell).
SHARED = ART_TESTS / "cells" / "_shared"


def fetch(log: RunLog, url: str, dest: pathlib.Path) -> pathlib.Path:
    """Downloads `url` to `dest` unless it is already there. Timed as a machine step.

    Only used for the free-asset sources agreed for this project (Kenney, Quaternius via
    Poly Pizza, Khronos samples, ambientCG, Poly Haven). Each cell lists what it took and
    under which licence in its CREDITS.md.
    """
    import urllib.request
    if dest.is_file() and dest.stat().st_size > 0:
        log.add_step(f"fetch {dest.name} (already here)", 0.0)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with log.step(f"fetch {dest.name}"):
        # Some hosts refuse requests without a browser-like User-Agent header.
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (asset-pipeline-test)"})
        with urllib.request.urlopen(request, timeout=120) as response:
            dest.write_bytes(response.read())
    return dest


def gate_model(log: RunLog, glb: pathlib.Path, **options) -> dict:
    """Runs gate3d on a model, saves turnaround renders under runs/, and attaches the report.

    **options are passed straight through to gate3d.run_gate (kind=, height=, clips=, ...).
    """
    renders = ART_TESTS / "runs" / "turnaround" / glb.stem
    with log.step(f"gate {glb.name}"):
        report = gate3d.run_gate(glb, render_dir=renders, **options)
    report.pop("facts", None)          # the full clip list of a 45-clip character bloats report.json
    # Reports are committed: keep machine-specific absolute paths out of them.
    # as_posix() writes a path with forward slashes on every operating system.
    here = (ART_TESTS.as_posix(), str(ART_TESTS))
    for item in report["checks"]:
        detail = str(item["detail"])
        for prefix in here:
            detail = detail.replace(prefix, "art_tests")
        item["detail"] = detail
    log.add_gate(report)
    return report


def write_credits(cell_dir: pathlib.Path, rows: list[tuple]) -> None:
    """Writes <cell>/CREDITS.md from (asset, author, source, licence) rows."""
    lines = ["# Credits", "", "Downloaded assets used by this cell. Nothing here was AI-generated.", "",
             "| Asset | Author | Source | Licence |", "|---|---|---|---|"]
    lines += [f"| {asset} | {author} | {source} | {licence} |" for asset, author, source, licence in rows]
    (cell_dir / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

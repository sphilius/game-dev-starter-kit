"""scoreboard.py - turns every cell's report.json into one table: SCOREBOARD.md.

    python scoreboard.py            # rewrite SCOREBOARD.md
    python scoreboard.py --check    # exit 1 if a cell is missing, fails a gate, or the file is stale

Each cell of the test matrix (cells/<genre>_<2d|3d>/) writes a report.json when its build.py
runs. This script only reads those files and the spend ledger; it measures nothing itself,
so the numbers here are exactly the numbers the runs recorded.

What the columns mean (also printed at the top of SCOREBOARD.md):
  machine   seconds the computer worked: generation, cleanup, Blender, Godot import, gates
  human     seconds a person is needed. ESTIMATES: 20 s per look at an output, plus a stated
            guess for each manual step (searching a site, tuning numbers by eye)
  looks     approvals: times a person must look at something and say yes
  re-rolls  outputs thrown away and made again
  cost      estimated dollars of paid image generation
"""
import csv
import json
import pathlib
import sys

ART_TESTS = pathlib.Path(__file__).resolve().parent
CELLS = ART_TESTS / "cells"
OUT = ART_TESTS / "SCOREBOARD.md"
GENRES = ("fps", "action_rpg", "tactics", "fighter", "metroidvania", "platformer")
GENRE_NAMES = {"fps": "FPS", "action_rpg": "Action RPG", "tactics": "Tactics", "fighter": "Fighter",
               "metroidvania": "Metroidvania", "platformer": "Platformer"}


def load_reports() -> dict:
    """Reads every cells/*/report.json. Returns {cell name: report dict}."""
    reports = {}
    for path in sorted(CELLS.glob("*/report.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        reports[report["cell"]] = report
    return reports


def gate_counts(report: dict) -> tuple[int, int, int]:
    """(passed, failed, skipped) over every check of every gated asset in a cell."""
    verdicts = [check["passed"] for gate in report["gates"] for check in gate["checks"]]
    # verdicts hold True / False / None; count() counts exact matches.
    return verdicts.count(True), verdicts.count(False), verdicts.count(None)


def art_source(report: dict) -> str:
    """One word for where the cell's art came from: generated, downloaded, or downloaded + built."""
    if report["spends"]:
        return "generated"
    return "downloaded + built" if "pipeline3d" in report["pipeline"] else "downloaded"


def minutes(seconds: float) -> str:
    """Seconds as a short "m:ss" string (65 -> "1:05")."""
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def cell_row(name: str, report: dict) -> str:
    """One table row for a cell."""
    passed, failed, skipped = gate_counts(report)
    images = sum(int(spend["images"]) for spend in report["spends"])
    gates = f"{passed} pass" + (f", **{failed} FAIL**" if failed else "") + (f", {skipped} n/a" if skipped else "")
    total = report["machine_seconds"] + report["human_seconds"]
    return (f"| [{name}](cells/{name}/screenshot.png) | {art_source(report)} | {images or '-'} | "
            f"${report['cost_usd']:.2f} | {minutes(report['machine_seconds'])} | {minutes(report['human_seconds'])} | "
            f"**{minutes(total)}** | {report['approvals']} | {report['rerolls']} | {gates} |")


def ledger_total() -> tuple[float, int]:
    """(dollars, images) summed over the whole spend ledger, including the preflight test image."""
    with open(ART_TESTS / "logs" / "spend_log.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return round(sum(float(row["est_cost_usd"] or 0) for row in rows), 2), sum(int(row["images"] or 0) for row in rows)


def build(reports: dict) -> str:
    """The whole SCOREBOARD.md as one string."""
    dollars, images = ledger_total()
    lines = [
        "# Art pipeline scoreboard",
        "",
        "Written by `scoreboard.py` from each cell's `report.json`. Do not edit by hand: re-run the script.",
        "",
        "One hero asset and one environment piece per cell, gated and placed in a running demo scene.",
        "Click a cell name to see its screenshot.",
        "",
        "- **machine**: time the computer worked (generation, cleanup, Blender, Godot import, gates), min:sec.",
        "- **human (est.)**: time a person is needed. These are ESTIMATES, not stopwatch readings: 20 s per",
        "  look at an output, plus a stated guess for each manual step. Writing the demo scene is not included.",
        "- **looks**: times a person must look at an output and say yes. **re-rolls**: outputs thrown away.",
        "- **gates**: checks from `gates/gate2d.py` and `gates/gate3d.py` on the final assets.",
        "",
        "| Cell | Art source | Images | Cost | Machine | Human (est.) | Total | Looks | Re-rolls | Gates |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for dimension in ("2d", "3d"):
        for genre in GENRES:
            name = f"{genre}_{dimension}"
            lines.append(cell_row(name, reports[name]) if name in reports else f"| {name} | **not run** | | | | | | | | |")
    machine = sum(r["machine_seconds"] for r in reports.values())
    human = sum(r["human_seconds"] for r in reports.values())
    lines += [
        "",
        f"**All {len(reports)} cells:** machine {minutes(machine)}, human (est.) {minutes(human)}, "
        f"{sum(r['rerolls'] for r in reports.values())} re-rolls, "
        f"${sum(r['cost_usd'] for r in reports.values()):.2f} of generation.",
        f"**Spend ledger** (`logs/spend_log.csv`): ${dollars:.2f} for {images} images, against a $5.00 cap.",
        "",
        "## What each cell used",
        "",
        "| Cell | Pipeline |",
        "|---|---|",
    ]
    lines += [f"| {name} | {report['pipeline']} |" for name, report in sorted(reports.items())]
    lines += ["", "## What went wrong (and is now written down)", ""]
    for name, report in sorted(reports.items()):
        problems = report["reroll_reasons"] + report["failure_modes"]
        if problems:
            lines.append(f"**{name}**")
            lines += [f"- {problem}" for problem in problems]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    """Writes SCOREBOARD.md, or with --check verifies it. Returns the exit code."""
    reports = load_reports()
    text = build(reports)
    if "--check" not in sys.argv:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.name}: {len(reports)} cells")
        return 0
    expected = {f"{genre}_{dimension}" for genre in GENRES for dimension in ("2d", "3d")}     # a set comprehension
    problems = [f"missing cell: {name}" for name in sorted(expected - set(reports))]
    problems += [f"{name}: gates failed {report['gates_failed']}" for name, report in reports.items()
                 if not report["gates_passed"]]
    if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
        problems.append("SCOREBOARD.md is out of date: run python scoreboard.py")
    for problem in problems:
        print("FAIL:", problem)
    print("scoreboard check:", "FAILED" if problems else "PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""show_report.py - prints one cell's report.json as a few readable lines.

    python show_report.py fps_2d

Handy after a build.py run: the headline numbers first, then every gate with its value.
"""
import json
import pathlib
import sys


def main(cell: str) -> None:
    """Loads <cell>/report.json and prints the headline numbers and each gate check."""
    report = json.loads((pathlib.Path(__file__).resolve().parent / cell / "report.json").read_text(encoding="utf-8"))
    for key in ("pipeline", "machine_seconds", "human_seconds", "approvals", "rerolls", "cost_usd",
                "gates_passed", "gates_failed", "failure_modes"):
        print(f"{key:16} {report[key]}")
    for gate in report["gates"]:
        print(f"-- {gate['asset']} ({gate['kind']})")
        for check in gate["checks"]:
            # None means the gate was skipped (tool missing or not relevant), not failed.
            verdict = {True: "pass", False: "FAIL", None: "skip"}[check["passed"]]
            print(f"   {verdict:4} {check['name']:16} {check['value']}  (limit {check['limit']})")


if __name__ == "__main__":
    main(sys.argv[1])

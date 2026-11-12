"""test_runlog.py - checks the run ledger: timings, counts, the report file and the budget cap.

    python test_runlog.py

Uses a throwaway spend log in a temp folder, so the real logs/spend_log.csv is never touched.
"""
import json
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import runlog  # noqa: E402


def check(condition: bool, message: str) -> None:
    """Stops the test with a clear message when a check fails."""
    if not condition:
        sys.exit(f"FAIL: {message}")


def test_report_contents(tmp: pathlib.Path) -> None:
    """Steps are timed and split into machine/human; counts and gate verdicts land in report.json."""
    ledger = tmp / "spend.csv"           # pathlib's "/" joins path parts
    # "with ... as log" calls RunLog.__enter__ now and __exit__ (which saves) at the end of the block.
    with runlog.RunLog("fps_2d", "test pipeline", tmp / "run1", spend_log=ledger) as log:
        with log.step("generate"):       # a nested "with": this step is timed until its block ends
            time.sleep(0.05)
        with log.step("review", human=True):
            time.sleep(0.02)
            log.approve("take 2")
        log.add_step("manual cleanup", 120, human=True)
        log.reroll("extra arm")
        log.reroll("wrong palette")
        log.spend(0.04, "gemini-api", "test-model", images=2)
        log.add_gate({"asset": "hero", "passed": True, "failed": []})
        log.add_gate({"asset": "wall", "passed": False, "failed": ["palette"]})
    report = json.loads((tmp / "run1" / "report.json").read_text())
    check(report["cell"] == "fps_2d" and report["pipeline"] == "test pipeline", "cell/pipeline missing")
    check(0.04 <= report["machine_seconds"] < 1.0, f"machine time wrong: {report['machine_seconds']}")
    check(120.0 <= report["human_seconds"] < 121.0, f"human time wrong: {report['human_seconds']}")
    check(report["approvals"] == 1 and report["rerolls"] == 2, "approval/re-roll counts wrong")
    check(report["cost_usd"] == 0.04, f"cost wrong: {report['cost_usd']}")
    check(report["gates_passed"] is False and report["gates_failed"] == ["wall:palette"],
          f"gate verdict wrong: {report['gates_failed']}")


def test_budget_cap(tmp: pathlib.Path) -> None:
    """The ledger adds up across runs and refuses a spend that would pass the cap."""
    ledger = tmp / "spend2.csv"
    first = runlog.RunLog("a", "p", tmp / "a", spend_log=ledger, budget_usd=0.10)
    first.spend(0.06, "svc")
    second = runlog.RunLog("b", "p", tmp / "b", spend_log=ledger, budget_usd=0.10)
    check(runlog.spent_so_far(ledger) == 0.06, "ledger total wrong after one spend")
    check(second.can_spend(0.04) and not second.can_spend(0.05), "can_spend is off")
    # try/except: the spend SHOULD raise. Reaching the check(False...) line means it did not.
    try:
        second.spend(0.05, "svc")
        check(False, "a spend past the cap should raise BudgetExceeded")
    except runlog.BudgetExceeded:
        pass                             # expected: the cap held
    check(runlog.spent_so_far(ledger) == 0.06, "a refused spend must not be written to the ledger")
    second.spend(0.04, "svc")
    # The CSV has a header row plus one row per spend; column 9 is running_total_usd.
    rows = ledger.read_text().strip().splitlines()
    check(len(rows) == 3 and rows[-1].split(",")[9] == "0.1", f"running total column wrong: {rows[-1]}")


def test_crash_still_saves(tmp: pathlib.Path) -> None:
    """If the pipeline throws, the report is still written and records the crash."""
    try:
        with runlog.RunLog("c", "p", tmp / "c", spend_log=tmp / "s3.csv") as log:
            with log.step("explode"):
                raise ValueError("boom")
    except ValueError:
        pass
    report = json.loads((tmp / "c" / "report.json").read_text())
    check(report["steps"][0]["ok"] is False, "failed step should be marked not ok")
    check(any("boom" in mode for mode in report["failure_modes"]), "crash not recorded in failure_modes")
    check(report["gates_passed"] is False, "a run with no gates must not count as passed")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        test_report_contents(pathlib.Path(folder))
        test_budget_cap(pathlib.Path(folder))
        test_crash_still_saves(pathlib.Path(folder))
    print("PASS")

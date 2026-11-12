"""runlog.py - the stopwatch and ledger for one art-pipeline run.

Every cell of the test matrix answers the same question: what did this asset really cost?
RunLog records the four numbers that decide whether a pipeline survives a jam:

    wall time        seconds per step, split into machine time and human time
    approvals        times a person had to look at something and say yes
    re-rolls         times an AI output was thrown away and generated again
    cost             dollars, also appended to logs/spend_log.csv with a hard cap

Use it as a context manager so the report is written even if a step crashes:

    with RunLog("fps_2d", "nano-banana billboard", out_dir) as log:
        with log.step("generate"):                 # timed automatically
            ...
        log.spend(0.02, "gemini-api", "gemini-3.1-flash-lite-image", images=1)
        log.reroll("hands merged with the weapon")
        with log.step("review", human=True):       # time a person spent
            log.approve("picked take 2")
        log.add_gate(gate2d.run_gate(...))

The result is <out_dir>/report.json, which scoreboard.py reads.
"""
import contextlib
import csv
import datetime
import json
import pathlib
import time

# The spend ledger shared by every run, and the budget agreed for the whole test matrix.
SPEND_LOG = pathlib.Path(__file__).resolve().parent.parent / "logs" / "spend_log.csv"
BUDGET_USD = 5.00
SPEND_COLUMNS = ["date", "cell", "purpose", "service", "model", "images", "resolution", "wall_s",
                 "est_cost_usd", "running_total_usd", "notes"]


class BudgetExceeded(RuntimeError):
    """Raised BEFORE a spend that would push the ledger past the budget, so the call can be skipped."""


def spent_so_far(spend_log: pathlib.Path = SPEND_LOG) -> float:
    """Total dollars already in the ledger (the sum of the est_cost_usd column)."""
    if not spend_log.is_file():
        return 0.0
    # "with open(...)" closes the file automatically; DictReader gives one dict per CSV row.
    with open(spend_log, newline="", encoding="utf-8") as handle:
        return round(sum(float(row["est_cost_usd"] or 0) for row in csv.DictReader(handle)), 4)


class RunLog:
    """Collects timings, approvals, re-rolls, cost and gate results for one pipeline run."""

    def __init__(self, cell: str, pipeline: str, out_dir: pathlib.Path,
                 spend_log: pathlib.Path = SPEND_LOG, budget_usd: float = BUDGET_USD) -> None:
        self.cell = cell
        self.pipeline = pipeline
        self.out_dir = pathlib.Path(out_dir)
        self.spend_log = spend_log
        self.budget_usd = budget_usd
        self.steps: list[dict] = []
        self.approvals: list[str] = []
        self.rerolls: list[str] = []
        self.spends: list[dict] = []
        self.gates: list[dict] = []
        self.notes: list[str] = []
        self.failure_modes: list[str] = []
        self._started = time.perf_counter()

    # __enter__/__exit__ are what make "with RunLog(...) as log:" work.
    def __enter__(self) -> "RunLog":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        """Always saves. A crash is recorded in the report and then re-raised (returning False)."""
        if exc is not None:
            self.failure_modes.append(f"run crashed: {exc_type.__name__}: {exc}")
        self.save()
        return False

    @contextlib.contextmanager
    def step(self, name: str, human: bool = False):
        """Times one step. `human=True` marks time a person spent (reviewing, clicking, fixing).

        @contextlib.contextmanager turns this generator into a "with" block: the code before
        `yield` runs on entry, the code in `finally` runs on exit, even after an error.
        """
        started = time.perf_counter()
        entry = {"name": name, "human": human, "seconds": 0.0, "ok": True}
        self.steps.append(entry)
        try:
            yield entry
        except Exception:
            entry["ok"] = False
            raise
        finally:
            entry["seconds"] = round(time.perf_counter() - started, 2)

    def add_step(self, name: str, seconds: float, human: bool = False) -> None:
        """Records a step timed some other way (for example a human estimate in minutes × 60)."""
        self.steps.append({"name": name, "human": human, "seconds": round(seconds, 2), "ok": True})

    def approve(self, note: str = "") -> None:
        """A person looked at an output and accepted it."""
        self.approvals.append(note)

    def reroll(self, reason: str) -> None:
        """An output was rejected and generated again. The reason feeds the failure-mode list."""
        self.rerolls.append(reason)

    def fail_mode(self, description: str) -> None:
        """Something that went wrong in a way worth warning future-you about."""
        self.failure_modes.append(description)

    def note(self, text: str) -> None:
        """Free-form context for the scoreboard."""
        self.notes.append(text)

    def can_spend(self, usd: float) -> bool:
        """True when `usd` more would still fit under the budget."""
        return spent_so_far(self.spend_log) + usd <= self.budget_usd + 1e-9

    # The only place money is recorded: one row here, one row in the shared CSV ledger.
    def spend(self, usd: float, service: str, model: str = "", images: int = 0, resolution: str = "",
              wall_s: float = 0.0, purpose: str = "", note: str = "") -> None:
        """Records a cost here and in the shared ledger. Refuses (BudgetExceeded) past the cap.

        Call can_spend() or this BEFORE making the paid request, so a refusal costs nothing.
        """
        total = spent_so_far(self.spend_log)
        if total + usd > self.budget_usd + 1e-9:
            raise BudgetExceeded(f"${usd:.2f} more would exceed the ${self.budget_usd:.2f} budget "
                                 f"(${total:.2f} already spent)")
        row = {"date": datetime.date.today().isoformat(), "cell": self.cell, "purpose": purpose or self.pipeline,
               "service": service, "model": model, "images": images, "resolution": resolution,
               "wall_s": round(wall_s, 1), "est_cost_usd": round(usd, 4),
               "running_total_usd": round(total + usd, 4), "notes": note}
        self.spends.append(row)
        self.spend_log.parent.mkdir(parents=True, exist_ok=True)
        is_new = not self.spend_log.is_file()
        with open(self.spend_log, "a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SPEND_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)

    def add_gate(self, report: dict) -> None:
        """Attaches a gate2d/gate3d report (its own "passed" decides the run's verdict)."""
        self.gates.append(report)

    def summary(self) -> dict:
        """The report as a dictionary (what save() writes)."""
        machine = sum(s["seconds"] for s in self.steps if not s["human"])
        human = sum(s["seconds"] for s in self.steps if s["human"])
        return {
            "cell": self.cell,
            "pipeline": self.pipeline,
            "date": datetime.date.today().isoformat(),
            "wall_seconds": round(time.perf_counter() - self._started, 2),
            "machine_seconds": round(machine, 2),
            "human_seconds": round(human, 2),
            "approvals": len(self.approvals),
            "rerolls": len(self.rerolls),
            "cost_usd": round(sum(s["est_cost_usd"] for s in self.spends), 4),
            "gates_passed": bool(self.gates) and all(g.get("passed") for g in self.gates),
            "gates_failed": [f"{g.get('asset', '?')}:{name}" for g in self.gates for name in g.get("failed", [])],
            "steps": self.steps,
            "approval_notes": self.approvals,
            "reroll_reasons": self.rerolls,
            "failure_modes": self.failure_modes,
            "notes": self.notes,
            "spends": self.spends,
            "gates": self.gates,
        }

    def save(self) -> pathlib.Path:
        """Writes <out_dir>/report.json and returns its path."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / "report.json"
        path.write_text(json.dumps(self.summary(), indent=2) + "\n", encoding="utf-8")
        return path

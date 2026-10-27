"""Use case: replay the lesson. Plans before, one index at a time, plans after, the write cost of each index."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..domain import lesson
from ..domain.errors import LessonInterruptedError
from ..domain.host import HostLoad
from ..domain.plan import PlanSummary, parse_text_plan
from ..domain.write_cost import WriteCost
from .ports import ArtifactStore, LabDatabase
from .report import render_results


@dataclass(frozen=True, slots=True)
class LessonResult:
    """Everything the replay measured."""

    plans: dict[str, PlanSummary]
    write_costs: tuple[tuple[str, WriteCost], ...]
    index_sizes: dict[str, int]
    host_load: HostLoad | None = None


class ReplayLesson:
    """Drives the database through the lesson's steps and keeps the evidence.

    `should_stop` is polled between steps; when it returns true the replay raises `LessonInterruptedError`, so a
    SIGTERM never leaves a half-applied step behind.
    """

    def __init__(
        self,
        database: LabDatabase,
        store: ArtifactStore,
        *,
        repetitions: int = 5,
        host_load: HostLoad | None = None,
        progress: Callable[[str], None] = lambda _message: None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self._database = database
        self._store = store
        self._repetitions = repetitions
        self._host_load = host_load
        self._progress = progress
        self._should_stop = should_stop

    def run(self) -> LessonResult:
        """Replay every step, write the plans and the notes, and return what was measured."""
        rows_before = self._database.row_count()
        self._database.reset_to(0)
        plans: dict[str, PlanSummary] = {}
        for name in lesson.BEFORE_ANY_INDEX:
            self._capture(name, plans)
        write_costs = [("no new indexes", self._measure())]
        for step in lesson.STEPS:
            self._checkpoint()
            self._progress(f"step {step.number}: {step.label}")
            self._database.apply_step(step.number)
            for name in step.captures:
                self._capture(name, plans)
            write_costs.append((step.label, self._measure()))
            self._database.vacuum()
        if self._database.row_count() != rows_before:
            raise AssertionError("the write-cost batches must be rolled back; the row count changed")
        result = LessonResult(plans, tuple(write_costs), dict(self._database.index_sizes()), self._host_load)
        self._store.save_report(render_results(result))
        return result

    def _capture(self, name: str, plans: dict[str, PlanSummary]) -> None:
        self._checkpoint()
        lines = self._database.capture_plan(name)
        self._store.save_plan(name, lines)
        plans[name] = parse_text_plan(lines)
        self._progress(f"plan {name}: {plans[name].execution_ms:.3f} ms, {plans[name].pages} pages")

    def _measure(self) -> WriteCost:
        self._checkpoint()
        return self._database.measure_write_cost(self._repetitions)

    def _checkpoint(self) -> None:
        if self._should_stop():
            raise LessonInterruptedError("stopped between steps")

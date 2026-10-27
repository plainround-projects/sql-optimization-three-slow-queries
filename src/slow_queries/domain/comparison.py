"""Before-and-after of one query: the ratio is what the lesson teaches, the milliseconds are only the evidence."""

from __future__ import annotations

from dataclasses import dataclass

from .plan import PlanSummary


@dataclass(frozen=True, slots=True)
class Improvement:
    """A plan before a change and the same query's plan after it."""

    before: PlanSummary
    after: PlanSummary

    @property
    def speedup(self) -> float:
        """How many times faster the query got; a zero-millisecond result counts as 0.001 ms."""
        return self.before.execution_ms / max(self.after.execution_ms, 0.001)

    @property
    def pages_ratio(self) -> float:
        """How many times fewer pages the query touches (at least one page after)."""
        return self.before.pages / max(self.after.pages, 1)

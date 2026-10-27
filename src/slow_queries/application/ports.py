"""Ports: what the use cases need from the outside world. Adapters in `infrastructure` implement them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from ..domain.write_cost import WriteCost


class LabDatabase(Protocol):
    """The orders table as the lesson changes it, one index at a time."""

    def reset_to(self, step: int) -> None:
        """Put the table in the state after migration `step` (0: only the primary key). Refreshes statistics."""
        ...

    def apply_step(self, number: int) -> None:
        """Apply migration `number` and refresh statistics. Raises `UnknownStepError` for a number the lesson lacks."""
        ...

    def capture_plan(self, name: str) -> tuple[str, ...]:
        """Run `explain/<name>.sql` once to warm the cache, again to measure, and return the measured plan's lines."""
        ...

    def measure_write_cost(self, repetitions: int) -> WriteCost:
        """The median cost of inserting 10,000 orders with the indexes now in place; the inserts are rolled back."""
        ...

    def vacuum(self) -> None:
        """Vacuum the orders table, so the visibility map and free space are current."""
        ...

    def row_count(self) -> int:
        """Rows in the orders table."""
        ...

    def index_sizes(self) -> Mapping[str, int]:
        """Size in bytes of each index of the orders table, by name."""
        ...


class ArtifactStore(Protocol):
    """Where the replay leaves its evidence: the captured plans and the results notes."""

    def save_plan(self, name: str, lines: Sequence[str]) -> None:
        """Keep the plan next to its query."""
        ...

    def save_report(self, text: str) -> None:
        """Keep the results notes."""
        ...


class HealthProbe(Protocol):
    """A dependency's health check."""

    name: str

    def check(self) -> str:
        """Return a short description of what is healthy. Raise `ProbeFailedError` when it is not."""
        ...

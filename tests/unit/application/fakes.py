"""In-memory stand-ins for the ports, so the replay can be tested without a database."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from slow_queries.domain.write_cost import WriteCost

PLAN_TEXT = ("Seq Scan on orders  (cost=0..1 rows=1)", "  Buffers: shared hit=100", "Execution Time: 10.0 ms")


class FakeDatabase:
    """Records every call; plans get faster as steps are applied and each index set costs more to write."""

    def __init__(self, rows: int = 1000, rows_after: int | None = None) -> None:
        self.calls: list[str] = []
        self._rows = rows
        self._rows_after = rows if rows_after is None else rows_after
        self._reads = 0

    def reset_to(self, step: int) -> None:
        self.calls.append(f"reset_to {step}")

    def apply_step(self, number: int) -> None:
        self.calls.append(f"apply_step {number}")

    def capture_plan(self, name: str) -> tuple[str, ...]:
        self.calls.append(f"capture {name}")
        return PLAN_TEXT

    def measure_write_cost(self, repetitions: int) -> WriteCost:
        self.calls.append(f"measure {repetitions}")
        return WriteCost(1.0, 10, 100, 1000)

    def vacuum(self) -> None:
        self.calls.append("vacuum")

    def row_count(self) -> int:
        self._reads += 1
        return self._rows if self._reads == 1 else self._rows_after

    def index_sizes(self) -> Mapping[str, int]:
        return {"idx_orders_listing": 60_000_000}


class RecordingStore:
    """Keeps what the replay saves."""

    def __init__(self) -> None:
        self.plans: dict[str, tuple[str, ...]] = {}
        self.report: str | None = None

    def save_plan(self, name: str, lines: Sequence[str]) -> None:
        self.plans[name] = tuple(lines)

    def save_report(self, text: str) -> None:
        self.report = text

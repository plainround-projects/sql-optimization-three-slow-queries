"""The price of an index on the write path: what 10,000 inserts cost with a given set of indexes."""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from .errors import PlanParseError
from .plan import pages_touched

_WAL = re.compile(r"WAL: records=(\d+).* bytes=(\d+)")
_EXECUTION = re.compile(r"Execution Time: ([\d.]+) ms")


@dataclass(frozen=True, slots=True)
class WriteCost:
    """Median cost of one batch of inserts. Pages touched and WAL records are the stable figures."""

    milliseconds: float
    pages: int
    wal_records: int
    wal_bytes: int


def parse_write_cost(lines: Sequence[str]) -> WriteCost:
    """Read one `EXPLAIN (ANALYZE, BUFFERS, WAL) INSERT ...` plan."""
    text = "\n".join(lines)
    wal, execution = _WAL.search(text), _EXECUTION.search(text)
    if wal is None or execution is None:
        raise PlanParseError("the insert plan has no WAL line or no Execution Time: was WAL requested?")
    return WriteCost(float(execution.group(1)), pages_touched(lines), int(wal.group(1)), int(wal.group(2)))


def median_cost(samples: Sequence[WriteCost]) -> WriteCost:
    """The median of each figure over repeated batches."""
    if not samples:
        raise ValueError("at least one sample is needed")
    return WriteCost(
        milliseconds=statistics.median(sample.milliseconds for sample in samples),
        pages=int(statistics.median(sample.pages for sample in samples)),
        wal_records=int(statistics.median(sample.wal_records for sample in samples)),
        wal_bytes=int(statistics.median(sample.wal_bytes for sample in samples)),
    )

"""Adapter: the orders table in PostgreSQL, changed by the repository's migration files. Implements `LabDatabase`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..domain.errors import UnknownStepError
from ..domain.lesson import INDEX_NAMES
from ..domain.plan import PlanSummary, parse_json_plan
from ..domain.write_cost import WriteCost, median_cost, parse_write_cost
from .logging import fields
from .postgres import scalar, session
from .settings import PostgresSettings
from .sql_script import run_file

logger = logging.getLogger(__name__)


class PostgresLabDatabase:
    """Runs the files in `sql/` against the compose database; opens a connection per operation."""

    def __init__(self, settings: PostgresSettings, sql_dir: Path) -> None:
        self._settings = settings
        self._sql_dir = sql_dir

    # -- migrations -----------------------------------------------------------------------------------------
    def migrations(self) -> list[Path]:
        """The up migrations in order (down scripts live in `migrations/down/`)."""
        return sorted((self._sql_dir / "migrations").glob("*.sql"))

    def down_migrations(self) -> list[Path]:
        """The down scripts in order."""
        return sorted((self._sql_dir / "migrations" / "down").glob("*.sql"))

    def apply_step(self, number: int) -> None:
        """Apply up migration `number` (1-based) and refresh statistics."""
        files = self.migrations()
        if not 1 <= number <= len(files):
            raise UnknownStepError(f"the lesson has migrations 1 to {len(files)}, not {number}")
        with session(self._settings) as connection:
            run_file(connection, files[number - 1])
            connection.execute("ANALYZE orders")
        logger.info("applied migration", extra=fields(number=number, file=files[number - 1].name))

    def revert_step(self, number: int) -> None:
        """Apply the down script of migration `number` (1-based)."""
        files = self.down_migrations()
        if not 1 <= number <= len(files):
            raise UnknownStepError(f"the lesson has down scripts 1 to {len(files)}, not {number}")
        with session(self._settings) as connection:
            run_file(connection, files[number - 1])
            connection.execute("ANALYZE orders")

    def reset_to(self, step: int) -> None:
        """Drop every lesson index, then apply migrations 1 to `step`."""
        with session(self._settings) as connection:
            for index in INDEX_NAMES:
                connection.execute(f"DROP INDEX IF EXISTS {index}")
            for path in self.migrations()[:step]:
                run_file(connection, path)
            connection.execute("ANALYZE orders")

    # -- plans ----------------------------------------------------------------------------------------------
    def capture_plan(self, name: str) -> tuple[str, ...]:
        """Run `explain/<name>.sql` twice (the first run warms the cache) and return the second plan's lines."""
        path = self._sql_dir / "explain" / f"{name}.sql"
        with session(self._settings) as connection:
            run_file(connection, path)
            rows = run_file(connection, path)
        return tuple(row[0] for row in rows)

    def explain_json(self, query: str) -> PlanSummary:
        """Plan a query with real timings and buffers and summarize it."""
        with session(self._settings) as connection:
            document: dict[str, Any] = scalar(connection, "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)[0]
        return parse_json_plan(document)

    def measure_write_cost(self, repetitions: int) -> WriteCost:
        """Insert 10,000 orders `repetitions` times under EXPLAIN (ANALYZE, BUFFERS, WAL), rolling each one back."""
        batch = (self._sql_dir / "bench" / "insert_10000_orders.sql").read_text().strip().rstrip(";")
        samples: list[WriteCost] = []
        with session(self._settings, autocommit=False) as connection:
            for attempt in range(repetitions + 1):  # attempt 0 is a warm-up and is not kept
                rows = connection.execute("EXPLAIN (ANALYZE, BUFFERS, WAL) " + batch).fetchall()
                connection.rollback()
                if attempt:
                    samples.append(parse_write_cost([row[0] for row in rows]))
        return median_cost(samples)

    # -- facts ----------------------------------------------------------------------------------------------
    def vacuum(self) -> None:
        with session(self._settings) as connection:
            connection.execute("VACUUM orders")

    def row_count(self) -> int:
        with session(self._settings) as connection:
            row = connection.execute("SELECT count(*) FROM orders").fetchone()
        return int(row[0]) if row else 0

    def index_sizes(self) -> dict[str, int]:
        with session(self._settings) as connection:
            rows = connection.execute(
                "SELECT indexrelname, pg_relation_size(indexrelid) FROM pg_stat_user_indexes WHERE relname = 'orders'"
            ).fetchall()
        return {name: int(size) for name, size in rows}

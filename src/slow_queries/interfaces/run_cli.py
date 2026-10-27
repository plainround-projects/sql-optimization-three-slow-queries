"""Replay the lesson: plans before, each index in turn, plans after, the write cost of each index.

python -m slow_queries.interfaces.run_cli [--output-dir DIR] [--repetitions N]
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from ..application.replay import ReplayLesson
from ..domain.errors import LabError, LessonInterruptedError
from ..infrastructure.artifacts import FileArtifactStore
from ..infrastructure.lab_database import PostgresLabDatabase
from ..infrastructure.logging import fields
from ..infrastructure.shutdown import ShutdownSignal
from .common import load_settings, measure_host_load

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the replay. Exit codes: 0 done, 1 lab error, 2 bad configuration, 130 interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="where plans and results.md go (default: sql/explain)")
    parser.add_argument("--repetitions", type=int, default=5, help="write-cost batches per index set (default 5)")
    arguments = parser.parse_args(argv)
    settings = load_settings()
    if settings is None:
        return 2
    shutdown = ShutdownSignal()
    shutdown.install()
    store = FileArtifactStore(arguments.output_dir or settings.sql_dir / "explain")
    replay = ReplayLesson(
        PostgresLabDatabase(settings.postgres, settings.sql_dir),
        store,
        repetitions=arguments.repetitions,
        host_load=measure_host_load(),
        progress=lambda message: logger.info(message),
        should_stop=lambda: shutdown.requested,
    )
    try:
        result = replay.run()
    except LessonInterruptedError:
        logger.warning("interrupted; the table is left between two steps, rerun to start clean")
        return 130
    except LabError as error:
        logger.error("the lesson failed", extra=fields(error=error))
        return 1
    for label, cost in result.write_costs:
        print(f"{label:62} {cost.milliseconds:8.1f} ms {cost.pages:8} pages {cost.wal_records:8} WAL records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

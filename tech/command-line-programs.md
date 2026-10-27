# Command-line programs, exit codes and signals

## What it is

A **command-line program** is started by typing its name and some words (**arguments**) in a terminal. It reads its settings from those arguments and from **environment variables**, prints results, and ends with an **exit code**. This note explains the mechanics that make the programs in this repository behave well: argument parsing, exit codes, standard streams, and **signals** (messages that the operating system or another program sends to a running process).

## Why this repository uses it

The lab is two programs: one replays the lesson (`slow-queries-run`), one checks that the database is ready (`slow-queries-health`). Their exit codes are their contract with `make`, with Docker's `HEALTHCHECK` and with the tests; the replay must stop cleanly when you press Ctrl-C.

## Where it appears

| File | Role |
|---|---|
| `interfaces/run_cli.py` | The replay command, with `argparse`. |
| `interfaces/health_cli.py` | The health command. |
| `interfaces/common.py` | Shared start-up that returns `None` on bad configuration. |
| `infrastructure/shutdown.py` | The signal flag. |
| `pyproject.toml` | `[project.scripts]` names the commands. |
| `Dockerfile` | `HEALTHCHECK` and `CMD` use the health command. |

## How it works underneath

**A process** is one running copy of a program. It has a number (the **PID**), three standard streams (input, output, error) and an exit code when it ends.

**Arguments.** The words after the program name arrive as a list of text (`sys.argv`). The standard module `argparse` turns them into named values: `parser.add_argument("--repetitions", type=int, default=5)` declares an optional argument `--repetitions N` whose text is converted to an int; `parser.parse_args(argv)` returns an object with the values, prints a usage message and exits with code 2 if something is wrong, and handles `--help` by itself.

**Exit codes.** The number a process returns to its parent: 0 means success, anything else means a problem. By common convention: 1 is a general failure, 2 is a usage or configuration error, and `128 + N` means "killed by signal N" (130 is `128 + 2`, the usual code after Ctrl-C). In Python, `sys.exit(n)` or `raise SystemExit(n)` ends the program with code `n`. A script uses `raise SystemExit(main())` so the number that `main` returns becomes the exit code.

**Where the program is started.** `python -m package.module` runs a module as the main program. A `[project.scripts]` entry creates a launcher that calls a function and exits with its result.

**Standard output and standard error.** Results go to standard output, diagnostics to standard error. A caller can capture one without the other.

**Signals.** The operating system can send a process a signal. `SIGINT` (number 2) is sent when you press Ctrl-C. `SIGTERM` (15) is the polite "please stop" that `docker stop` and process managers send. By default both kill the process at once. A program can install a **handler**, a function that runs instead: `signal.signal(signal.SIGTERM, handler)`. A handler should do very little; the common pattern is to set a **flag** that the main work checks between steps, so the program can finish the current step, release resources and exit cleanly. `threading.Event` is a thread-safe flag: `.set()` raises it, `.is_set()` reads it.

**Why graceful shutdown matters.** A program killed in the middle of an operation can leave half-done work behind. Stopping between two steps leaves a clear state.

## Walkthrough of this repository's use

### The health command

`src/slow_queries/interfaces/health_cli.py`, lines 1 to 27:

```python
"""Health command: exit 0 when PostgreSQL holds the seeded orders table.

python -m slow_queries.interfaces.health_cli
"""

from __future__ import annotations

from collections.abc import Sequence

from ..application.health import check_health
from ..infrastructure.health_probes import PostgresOrdersProbe
from .common import load_settings


def main(_argv: Sequence[str] | None = None) -> int:
    """Check PostgreSQL; returns 0 when healthy, 1 when not, 2 when the configuration is unusable."""
    settings = load_settings()
    if settings is None:
        return 2
    report = check_health([PostgresOrdersProbe(settings.postgres)])
    for result in report.results:
        print(f"{'ok' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- Lines 1 to 4: the docstring shows how to run it by hand: `python -m slow_queries.interfaces.health_cli`.
- `main(_argv=None) -> int`: the command takes no arguments (the underscore says the parameter is unused). It returns an integer exit code: `2` if the settings are unusable, `0` if healthy, `1` if not.
- `load_settings()` returns `None` after printing `configuration error: ...` (for example, if `PGPASSWORD` is not set).
- `check_health([PostgresOrdersProbe(settings.postgres)])` runs the probe; the loop prints one line per result: `ok postgres: 1,000,000 orders, statistics fresh` or `FAIL postgres: ...`. The expression `'ok' if result.ok else 'FAIL'` picks the word.
- Lines 26 and 27: `if __name__ == "__main__": raise SystemExit(main())` — run as a program, the exit code is what `main` returned.

### The replay command

`src/slow_queries/interfaces/run_cli.py`, lines 1 to 58:

```python
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
```

- `argparse.ArgumentParser(description=__doc__)` makes the parser and uses the module's docstring as the help text. `add_argument("--output-dir", type=Path, help=...)` declares an option converted to a `Path`; if it is not given its value is `None`. `--repetitions` is an int with default 5. `parser.parse_args(argv)` reads `sys.argv` when `argv` is `None`.
- `settings = load_settings()`; `if settings is None: return 2`.
- `shutdown = ShutdownSignal(); shutdown.install()` installs the signal handlers (next section).
- `store = FileArtifactStore(arguments.output_dir or settings.sql_dir / "explain")`: use `--output-dir` if given, otherwise `sql/explain`.
- `ReplayLesson(...)` is created with `progress=lambda message: logger.info(message)` (each progress message becomes a log line) and `should_stop=lambda: shutdown.requested` (the flag is polled between steps).
- The `try`/`except`: `LessonInterruptedError` means a signal arrived; it logs a warning and returns `130`. `LabError` (a named error of this package) logs the failure and returns `1`. Anything else would be a bug and would show a traceback with exit code 1.
- After a successful run the command prints one line per index set to **standard output** (`print`), with `f"{label:62} {cost.milliseconds:8.1f} ms ..."`: `:62` pads the label to 62 characters, `:8.1f` right-aligns the number in 8 columns with one decimal. It returns `0`.
- The docstring documents the exit codes: 0 done, 1 lab error, 2 bad configuration, 130 interrupted.

### The shutdown flag

`src/slow_queries/infrastructure/shutdown.py`, lines 1 to 29:

```python
"""Graceful shutdown: SIGINT and SIGTERM set a flag the work loops check between units of work."""

from __future__ import annotations

import signal
import threading
from types import FrameType


class ShutdownSignal:
    """A flag that SIGINT and SIGTERM set, which work loops check between units of work."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def install(self) -> None:
        """Route SIGINT and SIGTERM to `request`, so in-flight work finishes and connections close."""
        for number in (signal.SIGINT, signal.SIGTERM):
            signal.signal(number, self._handle)

    def _handle(self, _number: int, _frame: FrameType | None) -> None:
        self.request()

    def request(self) -> None:
        self._requested.set()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()
```

`ShutdownSignal` wraps a `threading.Event`. `install` loops over `(signal.SIGINT, signal.SIGTERM)` and calls `signal.signal(number, self._handle)`, so both signals call `_handle(number, frame)` instead of killing the process (`frame` is the place in the code that was interrupted; it is ignored). `_handle` calls `request`, which sets the event. `requested` is a property that reads it. Nothing else happens in the handler, which is exactly the safe pattern. The replay then raises `LessonInterruptedError` at its next checkpoint.

### Shared start-up

`src/slow_queries/interfaces/common.py`, lines 13 to 21:

```python
def load_settings() -> Settings | None:
    """Read and validate the environment, configure logging, or print the problem and return None."""
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return None
    configure_logging(settings.log_level)
    return settings
```

Bad configuration is a normal outcome of a command line, not a crash: print one line on standard error, return `None`, and let `main` return `2`.

## Try it yourself

1. `make up db` then `make health; echo "exit=$?"` prints `ok postgres: 1,000,000 orders, statistics fresh` and `exit=0`.
2. `PGPASSWORD= .venv/bin/slow-queries-health; echo "exit=$?"` prints `configuration error: PGPASSWORD must be set and not empty (copy .env.example to .env)` and `exit=2`.
3. `make down` then `.venv/bin/slow-queries-health; echo "exit=$?"` (with your `.env` loaded) prints a `FAIL postgres: cannot query PostgreSQL: ...` line after a few retry warnings and `exit=1`.
4. `.venv/bin/python -m slow_queries.interfaces.run_cli --help` prints the usage with `--output-dir` and `--repetitions`.
5. Start `make run`, press Ctrl-C while it runs. The log shows a warning that it was interrupted, and `echo $?` right after a direct run of `.venv/bin/slow-queries-run` shows `130`.

## Mistakes people make

- Doing real work inside a signal handler.
- Returning exit code 0 after an error, so scripts and CI think it worked.
- Printing errors on standard output and mixing them with results.
- Calling `sys.exit()` deep inside a library function instead of returning to `main`.
- Forgetting that `docker stop` sends SIGTERM and kills with SIGKILL after 10 seconds if the program ignores it.

**How this repository avoids them.** The handler only sets a flag. Exit codes are documented and tested (`tests/unit/interfaces/test_cli.py`). Logs go to standard error and results to standard output. `main` returns codes; only the last two lines of each module turn the return value into an exit.

## Check yourself

1. What exit code means success? *0.*
2. What does 130 mean? *The process ended because of signal 2 (Ctrl-C): 128 + 2.*
3. What is a signal handler good for? *Setting a flag that the main loop checks, so the program can stop cleanly.*
4. Why do results go to standard output and logs to standard error? *So that redirecting or piping the results does not capture the logs.*
5. What does `raise SystemExit(main())` do? *Calls `main`, then ends the program with the number it returned as the exit code.*

## Further reading

- `argparse` tutorial (3.13): https://docs.python.org/3.13/howto/argparse.html
- `signal` module: https://docs.python.org/3.13/library/signal.html ; `threading.Event`: https://docs.python.org/3.13/library/threading.html#event-objects
- POSIX exit status and signals: https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_08_02

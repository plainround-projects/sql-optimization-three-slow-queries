# The Python standard library

## What it is

The **standard library** is the set of modules that come with Python itself, with nothing to install. You load one with `import`. This note covers the modules this repository uses for files, time, randomness, statistics and JSON. (Logging, command-line parsing, signals and regular expressions have notes of their own.)

## Why this repository uses it

The only third-party package at run time is `psycopg`. Files, retries, medians and time stamps all come from the standard library, which keeps the lock file to four lines.

## Where it appears

| File | Modules |
|---|---|
| `infrastructure/artifacts.py` | `pathlib` |
| `infrastructure/retry.py` | `random`, `time` |
| `infrastructure/sql_script.py` | `pathlib` and text methods |
| `infrastructure/settings.py` | `os`, `pathlib` (environment note) |
| `infrastructure/postgres.py` | `contextlib` |
| `infrastructure/lab_database.py` | `pathlib` (`glob`, `read_text`) |
| `domain/write_cost.py` | `statistics` |
| `interfaces/common.py` | `os.getloadavg`, `os.cpu_count` |
| `infrastructure/logging.py` | `json`, `datetime` (logging note) |
| `tests/` | `subprocess`, `os`, `sys`, `pathlib`, `dataclasses` |

## How it works underneath

**`pathlib`.** A `Path` object stands for a file or folder path. `Path("a") / "b.txt"` joins parts with the right separator (`a/b.txt`). Useful members: `.name` (last part), `.parent`, `.parents[i]` (ancestors), `.resolve()` (make absolute, follow links), `.exists()`, `.read_text()` (whole file as text), `.write_text(text)`, `.mkdir(parents=True, exist_ok=True)` (create the folder and missing parents, no error if it exists), `.glob("*.sql")` (files matching a pattern), `__file__` (the path of the current module).

**`os`.** `os.environ` is the dictionary of environment variables. `os.getloadavg()` returns the system's load averages over 1, 5 and 15 minutes (a measure of how many programs were waiting to run). `os.cpu_count()` returns the number of CPUs or `None`.

**`sys`.** `sys.stderr` is the standard error stream; `sys.executable` is the path of the running Python; `sys.argv` the command-line words.

**`time`.** `time.sleep(seconds)` pauses the program. `time.perf_counter()` is a clock for measuring durations.

**`random`.** `random.Random()` makes a random-number generator object; `.uniform(a, b)` returns a random decimal between `a` and `b`. Passing a fixed seed makes the numbers repeatable, which tests rely on.

**`statistics`.** `statistics.median(numbers)` is the middle value of the sorted numbers (the average of the two middle ones if there is an even count).

**`json`.** `json.dumps(value)` turns a Python value into JSON text (text with quotes, braces and brackets); `json.loads(text)` does the opposite.

**`datetime`.** `datetime.fromtimestamp(seconds, tz=UTC)` converts a Unix timestamp (seconds since 1970-01-01 00:00 UTC) to a date-time object in a stated time zone; `.isoformat(timespec="milliseconds")` prints it as `2026-10-27T12:00:00.123+00:00`.

**`contextlib.contextmanager`.** Turns a generator function with one `yield` into a context manager usable with `with`: code before `yield` is the set-up, the yielded value is what `as name` receives, and code after it (in `finally`) is the clean-up.

**`collections.abc`**, **`typing`** and **`dataclasses`**: see the typing and dataclasses notes.

## Walkthrough of this repository's use

### `infrastructure/artifacts.py`

`src/slow_queries/infrastructure/artifacts.py`, lines 1 to 21:

```python
"""Adapter: the replay's evidence as files next to the queries. Implements `ArtifactStore`."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class FileArtifactStore:
    """Writes `<name>.txt` plans and `results.md` into one directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save_plan(self, name: str, lines: Sequence[str]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / f"{name}.txt").write_text("\n".join(lines) + "\n")

    def save_report(self, text: str) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / "results.md").write_text(text)
```

`FileArtifactStore` keeps one folder (`self._directory`, a `Path`). `save_plan` first makes sure the folder exists (`mkdir(parents=True, exist_ok=True)`), then writes `name.txt` into it: `self._directory / f"{name}.txt"` joins the folder and the file name, and `.write_text("\n".join(lines) + "\n")` writes all the lines separated by line breaks, with a final one. `save_report` writes `results.md` the same way. Because it is a *class with these two methods and the same types*, it satisfies the `ArtifactStore` port (typing note).

### `infrastructure/retry.py`

`src/slow_queries/infrastructure/retry.py`, lines 1 to 38:

```python
"""Retry with exponential backoff and jitter for calls that cross the network."""

from __future__ import annotations

import random
import time
from collections.abc import Callable


def retry[T](
    operation: Callable[[], T],
    *,
    attempts: int,
    base_delay_seconds: float,
    retry_on: tuple[type[BaseException], ...],
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    max_delay_seconds: float = 10.0,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Call `operation` up to `attempts` times, doubling the pause after each failure in `retry_on`.

    The pause is `base * 2**(attempt - 1)` capped at `max_delay_seconds`, then scaled by a random
    factor in [0.5, 1.0] so many clients do not retry in step. The last failure is raised.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    jitter = rng or random.Random()
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retry_on as error:
            if attempt == attempts:
                raise
            if on_retry:
                on_retry(attempt, error)
            sleep(min(max_delay_seconds, base_delay_seconds * 2 ** (attempt - 1)) * jitter.uniform(0.5, 1.0))
    raise AssertionError("unreachable")  # pragma: no cover
```

- Imports: `random` and `time`, and `Callable` for types.
- Line 26: `if attempts < 1: raise ValueError(...)` refuses a nonsense argument.
- Line 28: `jitter = rng or random.Random()` uses the given generator or makes a new one (`or` returns the right side if the left is `None`).
- Line 29: `for attempt in range(1, attempts + 1):` counts 1, 2, ... up to `attempts`.
- Lines 30 to 37: try the operation; `return operation()` ends the function at the first success. `except retry_on as error:` catches only the error classes given. On the last attempt (`attempt == attempts`) a bare `raise` re-raises the same error. Otherwise it calls `on_retry` if given and sleeps.
- The pause is `min(max_delay_seconds, base_delay_seconds * 2 ** (attempt - 1)) * jitter.uniform(0.5, 1.0)`: `**` is "to the power of", so with a base of 0.5 s the delays are 0.5, 1, 2, 4... seconds, capped at `max_delay_seconds` (10 s), then multiplied by a random number between 0.5 and 1.0. This is **exponential backoff with jitter**: wait longer after each failure, and add randomness so that many clients do not all retry at the same instant.
- Line 38: `raise AssertionError("unreachable")  # pragma: no cover` documents that the loop always returns or raises; the comment tells the coverage tool to ignore the line.

### `infrastructure/sql_script.py`

`src/slow_queries/infrastructure/sql_script.py`, lines 1 to 40:

```python
"""Read the repository's SQL files and run them statement by statement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg


def split_statements(sql_text: str) -> list[str]:
    """Split SQL on semicolons, ignoring `--` comments and quoted text (enough for the files in `sql/`).

    psql meta-commands (lines starting with a backslash) are not SQL and are dropped.
    """
    lines = [line.split("--", 1)[0] for line in sql_text.splitlines() if not line.lstrip().startswith("\\")]
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for character in "\n".join(lines):
        if quote:
            quote = None if character == quote else quote
        elif character in ("'", '"'):
            quote = character
        elif character == ";":
            statements.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    return [statement for statement in statements if statement]


def run_file(connection: psycopg.Connection[Any], path: Path) -> list[Any]:
    """Run every statement of a file on one connection; return the rows of the last one that returns rows."""
    rows: list[Any] = []
    for statement in split_statements(path.read_text()):
        cursor = connection.execute(statement)
        if cursor.description:
            rows = cursor.fetchall()
    return rows
```

`split_statements` turns the text of a `.sql` file into separate statements.

- Line 16: `lines = [line.split("--", 1)[0] for line in sql_text.splitlines() if not line.lstrip().startswith("\\")]` is a list comprehension. `splitlines()` splits the text into lines. `line.lstrip().startswith("\\")` is true for a line whose first non-blank character is a backslash (`"\\"` is one backslash in Python source); those are `psql` meta-commands, not SQL, and are skipped. `line.split("--", 1)[0]` cuts the line at the first `--` (an SQL comment) and keeps the part before it.
- Lines 17 to 30: a small state machine. `quote` is `None` outside quotes or holds the quote character that opened the current quoted text. The loop walks every character of the joined text. Inside quotes (`if quote:`) it closes the quote when it sees the same character (`quote = None if character == quote else quote`). Outside quotes, a `'` or `"` opens one; a `;` ends the statement: the collected characters are joined, stripped of surrounding blanks and saved, and `continue` skips adding the semicolon itself. Every other character is added to `current`.
- Line 30 keeps only non-empty statements.

`run_file` runs each statement on one connection. `cursor = connection.execute(statement)` returns a cursor; `cursor.description` is `None` for statements that return no rows, so `if cursor.description:` tests "this statement returns rows", and then `fetchall()` collects them. The function returns the rows of the last statement that returned rows (used by `capture_plan` to get the plan lines).

### `statistics` in `domain/write_cost.py`

Explained in the Python note: `median_cost` calls `statistics.median(...)` four times.

### `contextlib` in `infrastructure/postgres.py`

`src/slow_queries/infrastructure/postgres.py`, lines 48 to 63:

```python
@contextmanager
def session(settings: PostgresSettings, *, autocommit: bool = True) -> Iterator[psycopg.Connection[Any]]:
    """A connection that is always closed, also when the block raises."""
    connection = connect(settings, autocommit=autocommit)
    try:
        yield connection
    finally:
        connection.close()


def scalar(connection: psycopg.Connection[Any], query: str) -> Any:
    """The first column of the first row of a query that must return one."""
    row = connection.execute(query).fetchone()
    if row is None:
        raise LookupError(f"query returned no row: {query[:60]}")
    return row[0]
```

`session` is a generator with one `yield`, decorated with `@contextmanager`. With `with session(settings) as connection:` the code before `yield` opens a connection, the yielded value becomes `connection`, and the `finally` block closes it even when the body raises. `scalar` returns the first column of the first row of a query, or raises `LookupError` if there is no row (the slice `query[:60]` limits the message to the first 60 characters).

## Try it yourself

1. `.venv/bin/python -c "from slow_queries.infrastructure.sql_script import split_statements as s; print(s('SELECT 1; -- c\nSELECT 2;'))"` prints `['SELECT 1', 'SELECT 2']`.
2. `.venv/bin/python -c "from slow_queries.infrastructure.sql_script import split_statements as s; print(s(\"SELECT 'a;b';\n\\\\gset\"))"` keeps the semicolon inside the quotes and drops the backslash command: it prints `["SELECT 'a;b'"]`.
3. `.venv/bin/python -c "import statistics; print(statistics.median([1, 9, 3]), statistics.median([1, 2, 3, 4]))"` prints `3 2.5`.
4. `.venv/bin/python -c "import os; print(os.getloadavg(), os.cpu_count())"` prints three load numbers and the CPU count.
5. `.venv/bin/python -c "from pathlib import Path; p=Path('sql')/'explain'; print(p, sorted(x.name for x in p.glob('q1*.sql')))"` prints `sql/explain ['q1_day_after.sql', 'q1_day_before.sql']`.

## Mistakes people make

- Building paths by joining strings with `/` (use `Path`).
- Forgetting `exist_ok=True` and getting an error when the folder is already there.
- Using `time.sleep` in a loop with a fixed delay when many clients retry together (use jitter).
- Using `random` for secrets (it is not secure; use `secrets`).
- Using `time.time()` to measure durations (it can jump; use `perf_counter`).

**How this repository avoids them.** Paths are always `Path` objects. Retries have jitter and a cap. Time is slept through an injectable function, so the unit tests do not wait. Files are written with `exist_ok=True`. Medians use the library function.

## Check yourself

1. What does `Path("a") / "b.txt"` give? *The path `a/b.txt` with the right separator for the operating system.*
2. What does `mkdir(parents=True, exist_ok=True)` do? *Creates the folder and any missing parents, and does nothing if it already exists.*
3. What does `statistics.median([1, 9, 3])` return? *3, the middle value after sorting (1, 3, 9).*
4. What does `os.cpu_count() or 1` give if the count is unknown? *1: `or` returns the right side when the left is `None`.*
5. What is a context manager for? *Guaranteeing set-up and clean-up around a block with `with`, also when an error happens.*

## Further reading

- Python Standard Library index (3.13): https://docs.python.org/3.13/library/index.html (`pathlib`, `os`, `time`, `random`, `statistics`, `json`, `datetime`, `contextlib`).

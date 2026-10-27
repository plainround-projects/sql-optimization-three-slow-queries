# psycopg 3

## What it is

**psycopg** (version 3) is the Python library that talks to a PostgreSQL server. Your Python code opens a **connection**, sends SQL text, and receives rows back as Python values. Underneath it uses **libpq**, the C library from PostgreSQL itself that implements the network protocol.

## Why this repository uses it

Everything the lab does to the database goes through psycopg: running the SQL files, asking for plans, measuring write cost, health checks. It is the only third-party package the programs need at run time (pinned as `psycopg==3.3.6` and `psycopg-binary==3.3.6`).

## Where it appears

| File | Use |
|---|---|
| `infrastructure/postgres.py` | `connect`, `session`, `scalar`: every connection is opened here. |
| `infrastructure/lab_database.py` | Runs migrations, plans, write-cost batches, vacuum, counts. |
| `infrastructure/health_probes.py` | The health queries and the translation of `psycopg.Error`. |
| `infrastructure/sql_script.py` | `run_file` runs statements on a connection. |
| `tests/integration/*` | Open connections to check results. |
| `pyproject.toml` | `dependencies = ["psycopg[binary]>=3.2,<4"]`. |
| `domain/` and `application/` | Never import psycopg: import-linter forbids it. |

## How it works underneath

**Connection.** `psycopg.connect(host=..., port=..., dbname=..., user=..., password=..., connect_timeout=...)` opens a network (TCP) connection to the server, which starts a dedicated server process for it, and logs in. `connect_timeout` limits how long to wait, in seconds. The keyword `options` passes server settings for the session in the form `-c name=value`.

**Cursor and `execute`.** A **cursor** sends a statement and holds its result. `connection.execute("SELECT ...")` is a shortcut: it creates a cursor, runs the statement and returns the cursor. `cursor.fetchone()` returns the next row (a Python tuple) or `None`; `fetchall()` returns all remaining rows as a list. `cursor.description` is `None` when the statement returns no rows (an `INSERT`, `CREATE INDEX`...) and describes the columns when it does.

**Parameters.** `execute("... WHERE id = %s", (5,))` sends the value separately from the statement text (the server substitutes it, "server-side binding"). Never build SQL by pasting user text into a string: that is how SQL injection happens. A table or index *name* cannot be a parameter; code that must put a name into SQL builds the text itself, from a fixed list.

**Transactions and autocommit.** A **transaction** is a group of statements that succeed or fail together. With `autocommit=False` (the default) psycopg opens a transaction before your first statement and keeps it open until you call `commit()` or `rollback()`, or leave a `with connection:` block. With `autocommit=True` each statement is its own transaction and is saved at once. Some commands cannot run inside a transaction (`VACUUM`, `CREATE INDEX CONCURRENTLY`), so they need autocommit.

**Types.** Python `int`, `str`, `float`, `datetime`, `Decimal`, `list`, `dict` (as JSON) are converted to and from PostgreSQL types automatically. A row is a tuple unless you ask for something else.

**Errors.** Base class `psycopg.Error`; `psycopg.OperationalError` for connection problems and server shutdowns; `psycopg.errors.QueryCanceled` when a statement hits `statement_timeout`; many others named after PostgreSQL error codes.

**Installing.** `pip install "psycopg[binary]"` installs `psycopg` plus `psycopg-binary`, a precompiled version bundled with libpq, which needs no compiler and no PostgreSQL client libraries. `psycopg[c]` builds from source. Plain `psycopg` is pure Python and needs a libpq installed on the system.

**Closing.** A connection holds a server process; close it (`connection.close()`) or use a `with` block.

## Walkthrough of this repository's use

### Opening a connection

`src/slow_queries/infrastructure/postgres.py`, lines 1 to 45:

```python
"""Adapter: connections to PostgreSQL, with a connect timeout, a statement timeout and retries with backoff."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg

from .logging import fields
from .retry import retry
from .settings import PostgresSettings

logger = logging.getLogger(__name__)


def connect(settings: PostgresSettings, attempts: int = 5, *, autocommit: bool = True) -> psycopg.Connection[Any]:
    """Open a connection; parallel query is off for the session so plans read the same on every server."""

    def open_connection() -> psycopg.Connection[Any]:
        return psycopg.connect(
            host=settings.host,
            port=settings.port,
            dbname=settings.database,
            user=settings.user,
            password=settings.password,
            connect_timeout=settings.connect_timeout_seconds,
            options=(
                f"-c statement_timeout={settings.statement_timeout_ms} "
                f"-c max_parallel_workers_per_gather={settings.max_parallel_workers_per_gather}"
            ),
            autocommit=autocommit,
        )

    return retry(
        open_connection,
        attempts=attempts,
        base_delay_seconds=0.5,
        retry_on=(psycopg.OperationalError,),
        on_retry=lambda attempt, error: logger.warning(
            "retrying database connection", extra=fields(attempt=attempt, error=error)
        ),
    )
```

- `connect(settings, attempts=5, *, autocommit=True)` returns a `psycopg.Connection[Any]`. It defines an inner function `open_connection` and passes it to `retry`.
- `psycopg.connect(...)` gets the host, port, database name (`dbname=`), user and password from the settings, `connect_timeout=settings.connect_timeout_seconds` (5 seconds by default) and `autocommit=autocommit`.
- `options=(f"-c statement_timeout={settings.statement_timeout_ms} " f"-c max_parallel_workers_per_gather={settings.max_parallel_workers_per_gather}")` (two adjacent strings joined) sets two server settings for this session only: `statement_timeout` (a statement that runs longer than 120,000 ms is cancelled) and `max_parallel_workers_per_gather` (0: no parallel workers, so plans read the same everywhere). This is why the Compose file and the connection both say `0`.
- `retry(open_connection, attempts=5, base_delay_seconds=0.5, retry_on=(psycopg.OperationalError,), on_retry=lambda attempt, error: logger.warning(...))` retries only connection failures, with exponential backoff (standard-library note), and logs each failed attempt.
- `session(...)` (lines 48 to 55) wraps the connection in a context manager that always closes it.
- `scalar(connection, query)` runs `connection.execute(query).fetchone()` and returns `row[0]` — the first column of the first row.

### Running files, plans and write cost

`src/slow_queries/infrastructure/lab_database.py`, lines 21 to 64:

```python
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

```

- The class opens a **new connection per operation** (`with session(self._settings) as connection:`), which keeps each step simple and independent.
- `migrations()` and `down_migrations()` list the files with `Path.glob("*.sql")` and `sorted(...)`, so `001_...` comes before `002_...`.
- `apply_step(number)` checks `1 <= number <= len(files)` (a chained comparison), raises `UnknownStepError` otherwise, runs the file with `run_file(connection, files[number - 1])` and then `connection.execute("ANALYZE orders")`, which refreshes the planner's statistics. With `autocommit=True` (the default of `session`) each statement is committed at once; the SQL files carry their own `BEGIN`/`COMMIT`.
- `reset_to(step)` drops all three lesson indexes with `DROP INDEX IF EXISTS {index}` (an f-string: index names cannot be parameters, and here they come from a fixed constant tuple, not from user input) and re-applies migrations `1..step` using the slice `self.migrations()[:step]`.

`src/slow_queries/infrastructure/lab_database.py`, lines 65 to 107:

```python
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
```

- `capture_plan(name)` runs `sql/explain/<name>.sql` **twice** on the same connection: the first run loads the data into the cache, the second is the measured one. `run_file` returns the rows of the last statement that returns rows, which are the lines of the plan; `tuple(row[0] for row in rows)` takes the first column of each row.
- `explain_json(query)` runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) <query>`; the single value comes back already parsed (psycopg turns PostgreSQL's `json` into Python lists and dicts); `[0]` takes the first element, the plan document.
- `measure_write_cost(repetitions)` opens a connection with `autocommit=False` so that a transaction stays open. It reads `bench/insert_10000_orders.sql`, removes the trailing `;` (`.strip().rstrip(";")`), and loops `repetitions + 1` times: `EXPLAIN (ANALYZE, BUFFERS, WAL) <insert>` runs the real insert, `connection.rollback()` undoes it, and attempt 0 (the warm-up) is not kept (`if attempt:`). The median over the kept samples is returned.
- `vacuum` runs `VACUUM orders` (needs autocommit). `row_count` reads one row; `int(row[0]) if row else 0`. `index_sizes` returns a dict of `{index name: bytes}` built by a dict comprehension from `pg_stat_user_indexes` and `pg_relation_size(indexrelid)`.

### Health probe

`src/slow_queries/infrastructure/health_probes.py`, lines 12 to 36:

```python
class PostgresOrdersProbe:
    """Healthy when PostgreSQL answers and the seeded orders table has rows and fresh statistics."""

    name = "postgres"

    def __init__(self, settings: PostgresSettings) -> None:
        self._settings = settings

    def check(self) -> str:
        try:
            with session(self._settings) as connection:
                if scalar(connection, "SELECT to_regclass('public.orders')") is None:
                    raise ProbeFailedError("the orders table is missing; run make db")
                rows = scalar(connection, "SELECT count(*) FROM orders")
                analyzed = scalar(
                    connection,
                    "SELECT coalesce(last_analyze, last_autoanalyze) FROM pg_stat_user_tables WHERE relname = 'orders'",
                )
        except psycopg.Error as error:
            raise ProbeFailedError(f"cannot query PostgreSQL: {error}") from error
        if rows == 0:
            raise ProbeFailedError("the orders table is empty; run make db")
        if analyzed is None:
            raise ProbeFailedError("the orders table has never been analyzed; run make db")
        return f"{rows:,} orders, statistics fresh"
```

Three queries: `to_regclass('public.orders')` returns `NULL` (Python `None`) when the table does not exist; `count(*)`; and the last analyze time from `pg_stat_user_tables`. Any `psycopg.Error` is turned into the application's `ProbeFailedError` with `raise ... from error`; so `application/` never sees psycopg.

## Try it yourself

(After `make up db`, with `.env` loaded: `set -a; . ./.env; set +a`.)

1. `make health` prints `ok postgres: 1,000,000 orders, statistics fresh`.
2. Ask the server three questions through a session. Run:

   ```bash
   .venv/bin/python - <<'EOF'
   from slow_queries.infrastructure.postgres import session
   from slow_queries.infrastructure.settings import Settings
   with session(Settings.from_env().postgres) as c:
       print(c.execute("select version()").fetchone()[0])
       print(c.execute("show statement_timeout").fetchone())
       print(c.execute("show max_parallel_workers_per_gather").fetchone())
   EOF
   ```

   (`python -` reads the program from standard input; `<<'EOF' ... EOF` is a **here-document**, a way to give a shell command several lines of input.) It prints the PostgreSQL version line (`PostgreSQL 18.x ...`), `('2min',)` and `('0',)`: the two session settings were passed through `options`.
3. `echo $?` after it prints `0`.
4. `.venv/bin/python -c "from slow_queries.infrastructure.lab_database import PostgresLabDatabase as P; from slow_queries.infrastructure.settings import Settings as S; s=S.from_env(); print(P(s.postgres, s.sql_dir).index_sizes())"` prints a dictionary with `orders_pkey` and its size in bytes.
5. `make down` and run command 2 again: you see four `retrying database connection` warnings with growing pauses (five attempts are made) and then a `psycopg.OperationalError`.

## Mistakes people make

- Building SQL with f-strings from user input.
- Leaving a transaction open (a default connection after `SELECT` is "idle in transaction", holding resources and blocking maintenance).
- Forgetting `commit()` and losing changes.
- Running `VACUUM` in a transaction (PostgreSQL refuses).
- Not closing connections.
- Assuming a fetched row is a dictionary (it is a tuple unless a row factory is chosen).

**How this repository avoids them.** Connections are always closed (`finally`). Only the migration files and the plan files are executed; no user text is pasted into SQL, and the one f-string (`DROP INDEX IF EXISTS {index}`) uses names from a constant tuple. `VACUUM` runs on an autocommit connection. The write-cost batches run in a transaction that is rolled back, and the replay checks that the row count did not change.

## Check yourself

1. What does `connection.execute(sql)` return? *A cursor holding the result.*
2. When does `cursor.description` equal `None`? *When the statement returns no rows.*
3. What does `autocommit=True` change? *Every statement is committed on its own; no transaction stays open.*
4. Why pass values as parameters (`%s`) and not paste them into the SQL? *To avoid SQL injection and quoting errors; the value never becomes part of the statement text.*
5. What is `psycopg-binary`? *A precompiled, self-contained implementation that makes `pip install` need no compiler or libpq.*

## Further reading

- Psycopg 3 documentation (3.3): https://www.psycopg.org/psycopg3/docs/ — "Basic module usage", "Transactions management", "Installation".
- PostgreSQL libpq connection parameters: https://www.postgresql.org/docs/18/libpq-connect.html#LIBPQ-PARAMKEYWORDS

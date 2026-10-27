# pytest

## What it is

**pytest** is a Python tool for writing and running **tests**: small functions that check that your code does what you think. You write a function whose name starts with `test_`, use the plain Python statement `assert condition` inside it, and run `pytest`. It finds all test functions, runs them, and reports which passed and which failed, with the values involved in the failing `assert`.

## Why this repository uses it

Every "Done when" line of the lesson is a test, and every rule of the quality bar that can be tested is tested. There are 72 unit tests (no database, about a third of a second), 14 integration tests (the real database) and 2 end-to-end tests (the real commands).

## Where it appears

| File | Role |
|---|---|
| `pyproject.toml` | `[tool.pytest.ini_options]`: where tests are, flags, markers. |
| `tests/unit/` | Fast tests of `domain`, `application`, `infrastructure` (without a database) and `interfaces`. |
| `tests/unit/application/fakes.py` | The fake database and fake store. |
| `tests/integration/conftest.py`, `test_lesson_outcomes.py` | Tests against the seeded database. |
| `tests/e2e/test_replay.py` | The commands as subprocesses. |
| `Makefile` | `test`, `test-integration`, `test-e2e`. |

## How it works underneath

**Discovery.** pytest walks the folders given (or `testpaths` from the configuration) and imports every file named `test_*.py` or `*_test.py`. In each it collects functions named `test_*` (and methods of classes named `Test*`).

**Assertions.** `assert a == b`. pytest rewrites the statement when it imports the test file so that, on failure, it prints what `a` and `b` were. Passing means the function returns without an error.

**Expected errors.** `with pytest.raises(SomeError, match="text"):` passes only if the block raises that error and its message matches the regular expression.

**Fixtures.** A **fixture** is a function marked `@pytest.fixture` that prepares something a test needs. A test asks for it by writing the fixture's name as a parameter, and pytest runs the fixture first and passes in the result. A fixture that uses `yield value` hands the value to the test and runs the code after `yield` as clean-up when the test ends. `scope="session"` creates the fixture once per run instead of once per test. Fixtures placed in a file called **`conftest.py`** are available to all tests in that folder and below.

**Built-in fixtures used here.**

- `tmp_path`: a fresh empty temporary folder (a `Path`) for each test.
- `monkeypatch`: changes things for one test and undoes them afterwards: `setenv`/`delenv` (environment variables), `setattr(obj, "name", value)` (replace an attribute).
- `capsys`: captures what the test prints; `capsys.readouterr()` returns `.out` and `.err`.

**Parametrization.** `@pytest.mark.parametrize("name", [v1, v2, ...])` runs the same test once per value.

**Markers.** `@pytest.mark.integration` tags a test; `pytestmark = pytest.mark.integration` at the top of a file tags all tests in it. `pytest -m integration` runs only the tagged tests. `--strict-markers` makes an unknown marker an error (catching typos); markers are declared in the configuration.

**Fakes.** A test double is a simple object that stands in for something heavy (a database). Tests of the use cases pass a **fake** with the same methods, so they run in milliseconds with no database.

**Test levels.** *Unit* tests check one piece with fakes. *Integration* tests use the real database. *End-to-end* tests start the real program and check its output and exit code.

**Reading the output.** `.` passed, `F` failed, `E` error in set-up, `s` skipped. The last line is the summary: `72 passed in 0.32s`. `-ra` adds a summary of every non-passing test. `-q` is quiet.

## Walkthrough of this repository's use

### Configuration

`pyproject.toml`, lines 57 to 63:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = [
    "integration: needs PostgreSQL from docker-compose.yml with the seeded orders table (make up db)",
    "e2e: replays the lesson through the command-line program against PostgreSQL",
]
```

`testpaths = ["tests"]`: run from the repository root, pytest looks only in `tests/`. `addopts = "-ra --strict-markers"` is added to every command line: `-ra` prints a summary line for every test that did not simply pass; `--strict-markers` rejects unknown markers. The two markers, `integration` and `e2e`, are declared here with a description (`pytest --markers` shows them). `make test` points pytest at `tests/unit` only; the other two targets select by marker.

### A plain unit test

`tests/unit/domain/test_plan.py`, lines 30 to 38:

```python
def test_a_sequential_scan_is_read_with_its_time_pages_and_discarded_rows():
    plan = parse_text_plan(SEQ_SCAN)
    assert plan.execution_ms == 384.711
    assert plan.pages == 47646 + 15479
    assert plan.node_types == ("Seq Scan",)
    assert plan.rows_removed_by_filter == 997252
    assert plan.heap_fetches is None
    assert plan.has_node("Seq Scan")
    assert not plan.has_node("Sort")
```

`SEQ_SCAN` (lines 6 to 13 of that file) is a list of text lines copied from a real plan. The test calls the function and checks each field with `assert`. `assert plan.execution_ms == 384.711` compares numbers; `assert not plan.has_node("Sort")` checks a negative. The test name is a full sentence, so a failure reads like a message.

### Expecting an error

`tests/unit/domain/test_plan.py`, lines 65 to 67:

```python
def test_a_plan_without_analyze_is_refused():
    with pytest.raises(PlanParseError, match="Execution Time"):
        parse_text_plan(["Seq Scan on orders  (cost=0.00..1.00 rows=1 width=1)"])
```

`with pytest.raises(PlanParseError, match="Execution Time"):` passes only if `parse_text_plan` raises that error and its message contains "Execution Time" (`match` is a regular expression searched in the message).

### Parametrize, monkeypatch, tmp_path and capsys

`tests/unit/infrastructure/test_settings.py`, lines 49 to 62:

```python
@pytest.mark.parametrize(
    "extra",
    [
        {"PGPORT": "0"},
        {"PGPORT": "five"},
        {"PGHOST": "  "},
        {"PG_STATEMENT_TIMEOUT_MS": "-1"},
        {"PG_PARALLEL_WORKERS_PER_GATHER": "-1"},
        {"LOG_LEVEL": "LOUD"},
    ],
)
def test_an_unusable_value_is_rejected_with_the_variable_name(extra):
    with pytest.raises(ConfigurationError, match=next(iter(extra))):
        Settings.from_env({**MINIMAL, **extra})
```

`@pytest.mark.parametrize("extra", [...])` runs the test six times, once for each dictionary: a bad port, a blank host, a negative timeout, a bad log level. Each run builds settings from a good minimal environment plus the bad value and expects `ConfigurationError` whose message contains the variable name (`next(iter(extra))` takes the first key of the dictionary).

`tests/unit/infrastructure/test_settings.py`, lines 65 to 67:

```python
def test_settings_read_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "from-the-process")
    assert Settings.from_env().postgres.password == "from-the-process"
```

`monkeypatch.setenv("PGPASSWORD", "from-the-process")` sets an environment variable only for this test, then undoes it.

`tests/unit/infrastructure/test_artifacts.py`, lines 1 to 13:

```python
from slow_queries.infrastructure.artifacts import FileArtifactStore


def test_a_plan_is_written_next_to_its_name(tmp_path):
    store = FileArtifactStore(tmp_path / "out")
    store.save_plan("q1_day_before", ["Seq Scan on orders", "Execution Time: 1.0 ms"])
    assert (tmp_path / "out" / "q1_day_before.txt").read_text() == "Seq Scan on orders\nExecution Time: 1.0 ms\n"


def test_the_report_is_written_as_results_md(tmp_path):
    store = FileArtifactStore(tmp_path)
    store.save_report("# Results\n")
    assert (tmp_path / "results.md").read_text() == "# Results\n"
```

`tmp_path` gives a fresh folder; the store writes into it and the test reads the files back. No cleanup is needed.

`tests/unit/interfaces/test_cli.py`, lines 9 to 22:

```python
def test_a_missing_password_is_a_configuration_error_with_exit_code_2(monkeypatch, capsys):
    monkeypatch.delenv("PGPASSWORD", raising=False)
    assert health_cli.main([]) == 2
    assert "PGPASSWORD" in capsys.readouterr().err
    assert run_cli.main([]) == 2


def test_the_run_command_replays_against_the_database_it_is_given(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")
    monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda _settings, _sql_dir: FakeDatabase())
    assert run_cli.main(["--output-dir", str(tmp_path), "--repetitions", "2"]) == 0
    assert (tmp_path / "results.md").exists()
    assert (tmp_path / "q1_day_before.txt").exists()
    assert "no new indexes" in capsys.readouterr().out
```

`monkeypatch.delenv("PGPASSWORD", raising=False)` removes the variable (without failing if it is not set). `capsys.readouterr().err` is the text the command wrote to standard error. In the second test `monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda _settings, _sql_dir: FakeDatabase())` replaces the real database class **inside the `run_cli` module** with a function that returns a fake, so the whole command runs without a database; the test then checks the exit code (`== 0`), the files written and the printed output.

### Test doubles

`tests/unit/application/fakes.py`, lines 1 to 57:

```python
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
```

`FakeDatabase` implements the same methods as the `LabDatabase` port but only records calls (`self.calls.append(...)`) and returns canned values (`PLAN_TEXT`, a fixed `WriteCost`). `RecordingStore` keeps what it is given. With them, `tests/unit/application/test_replay.py` can check the order of steps (`database.calls.index("apply_step 2")`), that plans are saved, that a changed row count is detected (`FakeDatabase(rows=1000, rows_after=1500)`) and that `should_stop` interrupts the replay.

### Other unit test files

- `tests/unit/domain/test_host.py`, `test_comparison_and_lesson.py`, `test_write_cost.py`: plain asserts on small values, including the guard against division by zero (`plan(0.0, 0)`).
- `tests/unit/application/test_health.py`: a tiny `Probe` class (a hand-made fake with `name` and `check`).
- `tests/unit/application/test_report.py`: calls `render_results` and checks that exact lines appear in the Markdown text.
- `tests/unit/infrastructure/test_retry.py`: a `Flaky` class that fails a set number of times; `sleep=pauses.append` records the pauses instead of sleeping, and `rng=random.Random(1)` makes the jitter repeatable; `zip(pauses, (1, 2, 4), strict=True)` pairs each pause with its ceiling and raises if the lengths differ.
- `tests/unit/infrastructure/test_logging_and_shutdown.py`: `io.StringIO()` is an in-memory text stream that receives the log lines; the SIGTERM test installs the handler, sends the process a real signal with `signal.raise_signal`, checks the flag and restores the old handlers in `finally`.
- `tests/unit/infrastructure/test_sql_script.py`: the last test walks every SQL file Python runs and checks that it splits into complete statements.

### Integration tests

`tests/integration/conftest.py`, lines 1 to 31:

```python
"""Fixtures for the tests that need the seeded database from `make up db`."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from slow_queries.infrastructure import postgres
from slow_queries.infrastructure.lab_database import PostgresLabDatabase
from slow_queries.infrastructure.settings import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def database(settings: Settings) -> Iterator[PostgresLabDatabase]:
    """The lab database; every test starts and ends with only the primary key in place."""
    lab = PostgresLabDatabase(settings.postgres, settings.sql_dir)
    lab.reset_to(0)
    yield lab
    lab.reset_to(0)


@pytest.fixture
def connection(settings: Settings) -> Iterator[psycopg.Connection[Any]]:
    with postgres.session(settings.postgres) as live:
        yield live
```

`@pytest.fixture(scope="session")` builds `Settings` once. The `database` fixture resets the table to "primary key only" before the test (`lab.reset_to(0)`), hands it over with `yield lab`, and resets again afterwards, so tests cannot affect one another. `connection` opens a session for the test.

`tests/integration/test_lesson_outcomes.py`, lines 12 to 12:

```python
pytestmark = pytest.mark.integration
```
`tests/integration/test_lesson_outcomes.py`, lines 50 to 57:

```python
def test_the_day_query_uses_the_index_and_is_ten_times_faster(database):
    before = database.explain_json(DAY_FUNCTION)
    database.apply_step(1)
    after = database.explain_json(DAY_RANGE)
    assert not after.has_node("Seq Scan")
    assert after.uses_index("idx_orders_created_at")
    assert before.execution_ms >= 10 * after.execution_ms
    assert before.pages >= 10 * after.pages, "the page count tells the same story as the clock"
```

`pytestmark = pytest.mark.integration` marks every test in the file. The test checks the day query against the real database: the plan after migration 1 does not scan the table sequentially, uses the new index, is at least ten times faster and touches at least ten times fewer pages.

### End-to-end tests

`tests/e2e/test_replay.py`, lines 1 to 40:

```python
"""The lesson's scenario through the command-line programs, as the Makefile runs them (make up db first)."""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.e2e

# A shared machine can take longer than the 5 s default to accept a connection while the replay runs.
SLOW_MACHINE = {"PG_CONNECT_TIMEOUT_SECONDS": os.environ.get("PG_CONNECT_TIMEOUT_SECONDS", "30")}


def program(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", f"slow_queries.interfaces.{module}", *args],
        capture_output=True,
        text=True,
        env={**os.environ, **SLOW_MACHINE},
        timeout=900,
        check=False,
    )


def test_the_health_command_is_green_on_the_seeded_database():
    result = program("health_cli")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok postgres: 1,000,000 orders" in result.stdout


def test_the_replay_writes_every_plan_and_a_results_table(tmp_path):
    result = program("run_cli", "--output-dir", str(tmp_path), "--repetitions", "1")
    assert result.returncode == 0, result.stderr
    notes = (tmp_path / "results.md").read_text()
    assert "| q1 day query |" in notes
    assert "| idx_orders_listing only (idx_orders_customer_created dropped) |" in notes
    assert "Seq Scan on orders" in (tmp_path / "q1_day_before.txt").read_text()
    assert "Index Only Scan using idx_orders_listing" in (tmp_path / "q3_listing_after.txt").read_text()
    assert len(list(tmp_path.glob("*.txt"))) == 11
```

`SLOW_MACHINE` (lines 11 and 12) is a dictionary with one environment variable, `PG_CONNECT_TIMEOUT_SECONDS`, defaulting to `30`: on a busy machine the commands get 30 seconds, not 5, to be accepted by the database. `{**os.environ, **SLOW_MACHINE}` builds the child's environment by copying the current one and adding that entry. `program(...)` starts the real command as a separate process with `subprocess.run([...], capture_output=True, text=True, env=..., timeout=900, check=False)`: capture the output as text, give it the environment, stop it after 15 minutes, and do not raise on a non-zero exit (the test checks `returncode` itself). The second test runs the whole replay into a temporary folder and checks the files it wrote.

## Try it yourself

1. `make test` — `72 passed` for the unit tests, then the coverage table, ending with a coverage report for the domain and application folders.
2. `.venv/bin/python -m pytest tests/unit/domain -q` — only the domain tests (the output ends `.. passed`).
3. `.venv/bin/python -m pytest tests/unit -q -k retry` — runs only tests whose name contains `retry`.
4. `.venv/bin/python -m pytest --markers | head` — lists the markers, including the project's two.
5. `.venv/bin/python -m pytest tests/unit/infrastructure/test_settings.py -q -x -vv` — verbose names; try breaking an assertion in a scratch copy to see pytest's explanation of the difference.
6. With the database up: `make test-integration` (14 tests, about a minute) and `make test-e2e` (2 tests, a few minutes).

## Mistakes people make

- A test that depends on another test running first.
- Tests that read the real clock, random numbers or the network and so fail sometimes.
- Asserting too little (a test that cannot fail).
- Catching the error inside the test instead of using `pytest.raises`.
- Leaving shared state (a database table) changed after a test.
- Naming a test file or function without the `test` prefix, so pytest never runs it.

**How this repository avoids them.** Unit tests never touch the network, the clock or the environment except through fixtures. Integration tests reset the table before and after. Markers are declared and `--strict-markers` is on. Failing-path tests use `pytest.raises` with `match`.

## Check yourself

1. How does pytest know which functions are tests? *They are named `test_*` in files named `test_*.py`.*
2. What is a fixture? *A function that prepares something for tests; a test receives it by naming it as a parameter.*
3. What does `tmp_path` give? *A new empty temporary folder, different for each test.*
4. What does `pytest -m integration` do? *Runs only the tests marked `integration`.*
5. What does `--strict-markers` protect against? *Misspelled or undeclared marker names being silently accepted.*

## Further reading

- pytest documentation (9.1): https://docs.pytest.org/en/stable/ — "Get Started", "How to use fixtures", "How to parametrize", "How to monkeypatch", "How to capture stdout/stderr".

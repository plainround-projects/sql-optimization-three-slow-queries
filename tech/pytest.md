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

### The unit tests that every repository shares, line by line

Three of the lab's helper modules are the same in all three repositories: the retry helper, the "how busy was the machine" note, the logging and shutdown helpers, and the health check. Their tests are the same too. This part walks through each file completely. Before the first one, three ideas that every test below uses.

- **A test is a function whose name starts with `test_`.** pytest finds it, calls it with no arguments, and counts it as passed if it returns normally and failed if anything inside it raises an error.
- **`assert` is a Python statement that raises an `AssertionError` when its condition is false.** Everything that "checks" something in these files is an `assert`, or a `with pytest.raises(...)` block that checks that an error does happen.
- **A test double is a stand-in object.** Instead of really sleeping for seconds, or really asking a database a question, a test hands the code under test a small replacement that records what it was asked, so the test is fast and gives the same answer every time.

#### `tests/unit/infrastructure/test_retry.py`

The code under test is `retry`, a function that calls an operation, and if the operation fails with one of a list of error types, waits a moment and tries again. The wait doubles after each failure (1 second, 2 seconds, 4 seconds, and so on) and is then multiplied by a random number between 0.5 and 1.0. That random part is called **jitter**: it stops many clients that failed at the same moment from all retrying at the same moment.

`tests/unit/infrastructure/test_retry.py`, lines 1 to 5:

```python
import random

import pytest

from slow_queries.infrastructure.retry import retry
```

Line 1 imports Python's `random` module, which supplies random numbers and, in the next lines, a random number generator we can seed. Line 3 imports `pytest`, which is needed for `pytest.raises`. Line 5 imports the function under test from the lab's own package. A blank line separates the three groups: the standard library, third-party packages, and this project's own code. That is the order the linter `ruff` enforces.

`tests/unit/infrastructure/test_retry.py`, lines 8 to 16:

```python
class Flaky:
    def __init__(self, failures: int) -> None:
        self.failures, self.calls = failures, 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("down")
        return "ok"
```

`Flaky` is a hand-made test double: an operation that fails a chosen number of times and then succeeds.

- `class Flaky:` starts a class, a blueprint for objects.
- `def __init__(self, failures: int) -> None:` is the constructor; Python runs it when you write `Flaky(3)`. `self` is the object being built. `: int` says the argument is a whole number and `-> None` says the function returns nothing; these are type hints that `mypy` checks but Python ignores while running.
- `self.failures, self.calls = failures, 0` stores two values on the object in one line: how many failures to produce, and a counter of calls so far, starting at zero.
- `def __call__(self) -> str:` is a special method name. It makes an object callable, so `Flaky(3)()` runs this method, exactly as if the object were a function. That is what lets `retry` take a `Flaky` where it expects an operation.
- `self.calls += 1` adds one to the counter every time the object is called.
- `if self.calls <= self.failures:` is true for the first `failures` calls, and then `raise ConnectionError("down")` stops the call with an error of that type. `ConnectionError` is a built-in Python error, the kind a database driver raises when the network drops.
- `return "ok"` is reached only on the later calls, which succeed.

`tests/unit/infrastructure/test_retry.py`, lines 19 to 22:

```python
def test_it_returns_the_first_success_without_sleeping():
    pauses: list[float] = []
    assert retry(Flaky(0), attempts=3, base_delay_seconds=1, retry_on=(ConnectionError,), sleep=pauses.append) == "ok"
    assert pauses == []
```

The first test: an operation that never fails (`Flaky(0)`) must come back with its answer and never wait. `pauses: list[float] = []` creates an empty list that will collect every pause the retry helper asks for. The argument `sleep=pauses.append` is the trick: `retry` normally calls `time.sleep` to wait, but here it is told to call `pauses.append` instead, which records the number and returns at once. The call also passes `attempts=3` (give up after three tries), `base_delay_seconds=1` (the first pause would be about one second) and `retry_on=(ConnectionError,)` (the tuple of error types that deserve a retry; the trailing comma makes it a one-item tuple). The line ends with `== "ok"`, so the `assert` checks the returned value. The second `assert` checks that the list of pauses is still empty.

`tests/unit/infrastructure/test_retry.py`, lines 25 to 39:

```python
def test_it_retries_with_doubling_pauses_inside_the_jitter_band():
    pauses: list[float] = []
    operation = Flaky(3)
    result = retry(
        operation,
        attempts=5,
        base_delay_seconds=1,
        retry_on=(ConnectionError,),
        sleep=pauses.append,
        rng=random.Random(1),
    )
    assert result == "ok"
    assert operation.calls == 4
    for pause, ceiling in zip(pauses, (1, 2, 4), strict=True):
        assert ceiling * 0.5 <= pause <= ceiling
```

The second test checks the doubling and the jitter band. `Flaky(3)` fails three times, so the fourth call succeeds. The call is spread over several lines because each argument is on its own line, which is how the formatter lays out a call that is too long for one line. `rng=random.Random(1)` hands `retry` a random number generator started with the **seed** 1. A seeded generator produces the same sequence every run, so the test cannot fail by bad luck. The asserts check that the final answer is `"ok"` and that `operation.calls == 4` (three failures plus the success). The loop `for pause, ceiling in zip(pauses, (1, 2, 4), strict=True):` walks the three recorded pauses together with the three values they may not exceed. `zip` pairs items from two sequences; `strict=True` makes `zip` raise an error if the two sequences have different lengths, which would mean `retry` slept the wrong number of times. Inside the loop, `assert ceiling * 0.5 <= pause <= ceiling` is Python's chained comparison: each pause must be at least half of its ceiling and at most the ceiling, which is the jitter band.

`tests/unit/infrastructure/test_retry.py`, lines 42 to 52:

```python
def test_the_pause_is_capped():
    pauses: list[float] = []
    retry(
        Flaky(4),
        attempts=6,
        base_delay_seconds=10,
        retry_on=(ConnectionError,),
        sleep=pauses.append,
        max_delay_seconds=15,
    )
    assert max(pauses) <= 15
```

The third test checks the cap. With a base delay of 10 seconds the doubled values would be 10, 20, 40 and 80, which is far too long to wait. `max_delay_seconds=15` tells `retry` never to pause longer than 15 seconds before the jitter is applied. `Flaky(4)` fails four times and `attempts=6` leaves room for the fifth call to succeed, so four pauses are recorded. `assert max(pauses) <= 15` takes the largest recorded pause and checks it against the cap. The test does not need a seeded generator, because jitter only shrinks a pause, so the bound holds for every random value.

`tests/unit/infrastructure/test_retry.py`, lines 55 to 59:

```python
def test_the_last_failure_is_raised_after_the_final_attempt():
    operation = Flaky(10)
    with pytest.raises(ConnectionError):
        retry(operation, attempts=3, base_delay_seconds=0, retry_on=(ConnectionError,), sleep=lambda _: None)
    assert operation.calls == 3
```

The fourth test checks what happens when every attempt fails. `Flaky(10)` fails ten times but only three attempts are allowed. `with pytest.raises(ConnectionError):` says "the code inside this block must raise a `ConnectionError`; if it raises nothing, or a different error, the test fails". The pause is `base_delay_seconds=0` and `sleep=lambda _: None` is a one-line function that takes one argument, named `_` because it is ignored, and does nothing; the test does not need to see the pauses, only to avoid waiting. After the block, `assert operation.calls == 3` proves the helper stopped after exactly three tries and raised the last error instead of looping on.

`tests/unit/infrastructure/test_retry.py`, lines 62 to 67:

```python
def test_other_errors_are_not_retried():
    def broken() -> str:
        raise KeyError("x")

    with pytest.raises(KeyError):
        retry(broken, attempts=3, base_delay_seconds=0, retry_on=(ConnectionError,), sleep=lambda _: None)
```

The fifth test checks that only the listed errors are retried. `broken` is a small function defined inside the test that always raises `KeyError("x")`. `retry_on` lists only `ConnectionError`, so a `KeyError` must not be caught: it must come straight out. The blank line after the function is required by the formatter. If `retry` had retried it, the test would still pass the error out after three tries, so the point here is the type: `pytest.raises(KeyError)` shows the original error, not a wrapped one, escapes.

`tests/unit/infrastructure/test_retry.py`, lines 70 to 80:

```python
def test_each_retry_is_reported():
    seen: list[int] = []
    retry(
        Flaky(2),
        attempts=4,
        base_delay_seconds=0,
        retry_on=(ConnectionError,),
        sleep=lambda _: None,
        on_retry=lambda attempt, _: seen.append(attempt),
    )
    assert seen == [1, 2]
```

The sixth test checks the `on_retry` hook, a function `retry` calls before each pause with the attempt number and the error. `seen: list[int] = []` collects the attempt numbers. `on_retry=lambda attempt, _: seen.append(attempt)` is a function that takes two arguments (the second is ignored) and records the first. With `Flaky(2)` the first two calls fail, so the hook is called for attempts 1 and 2 and not for the third, which succeeds. `assert seen == [1, 2]` checks exactly that.

`tests/unit/infrastructure/test_retry.py`, lines 83 to 85:

```python
def test_at_least_one_attempt_is_required():
    with pytest.raises(ValueError, match="attempts"):
        retry(Flaky(0), attempts=0, base_delay_seconds=0, retry_on=(ConnectionError,))
```

The last test checks the guard at the top of `retry`. Asking for zero attempts makes no sense, so the helper raises `ValueError`. `match="attempts"` is a regular expression that pytest searches for in the error's message; it makes sure the message names the bad argument. This call leaves out `sleep` because the helper must fail before it could ever sleep.

#### `tests/unit/domain/test_host.py`

The code under test is `HostLoad`, a small value object that holds the machine's load average (how many programs were waiting for a processor, averaged over the last minute) and the number of processors. It marks the machine as loaded when the load average is more than half the processor count. The lab prints a note about this next to every timing, because milliseconds measured on a busy computer are inflated.

`tests/unit/domain/test_host.py`, lines 1 to 1:

```python
from slow_queries.domain.host import HostLoad
```

The only import: the class under test. The `domain` folder never imports a database driver or the file system, which is why this test needs no setup at all.

`tests/unit/domain/test_host.py`, lines 4 to 7:

```python
def test_a_load_above_half_a_task_per_cpu_is_a_loaded_machine():
    assert HostLoad(40.0, 12).loaded
    assert not HostLoad(3.0, 12).loaded
    assert not HostLoad(6.0, 12).loaded
```

`HostLoad(40.0, 12)` builds a value with load average 40 and 12 CPUs. 40 is more than half of 12, so `.loaded` must be true and the first `assert` passes. `assert not HostLoad(3.0, 12).loaded` uses `not` to say the opposite: 3 is below 6, so the machine is not loaded. The third line tests the boundary: 6.0 on 12 CPUs is exactly half, and the rule is "more than half", so `loaded` is false. Testing the exact boundary is how a mistaken `>=` is caught.

`tests/unit/domain/test_host.py`, lines 10 to 14:

```python
def test_the_note_names_the_load_and_says_what_to_do_when_it_is_high():
    loaded = HostLoad(39.5, 12).note()
    assert "loaded machine (load average 39.5 on 12 CPUs)" in loaded
    assert "rerun `make run`" in loaded
    assert HostLoad(2.0, 12).note() == "Measured at load average 2.0 on 12 CPUs."
```

The second test checks the sentence written into the results file. `HostLoad(39.5, 12).note()` returns the loaded-machine message. `assert "..." in loaded` checks that a piece of text appears inside a longer text, which keeps the test from breaking if the wording around it changes. The two pieces checked are the measured numbers, `loaded machine (load average 39.5 on 12 CPUs)`, and the advice to rerun `make run`; the backticks around `make run` are part of the Markdown the note produces. The last line uses `==` because the quiet-machine sentence is short and fixed: `Measured at load average 2.0 on 12 CPUs.` has to match exactly.

#### `tests/unit/application/test_health.py`

The code under test is `check_health`, which takes a list of **probes** (objects with a `name` and a `check()` method that either returns a short text or raises `ProbeFailedError`) and returns a report that is healthy only if every probe passed. A failing probe must be reported, not allowed to crash the check.

`tests/unit/application/test_health.py`, lines 1 to 1:

```python
from slow_queries.application.health import ProbeFailedError, check_health
```

Imports the error class and the function. `ProbeFailedError` is imported because the test double raises it.

`tests/unit/application/test_health.py`, lines 4 to 11:

```python
class Probe:
    def __init__(self, name: str, error: str | None = None) -> None:
        self.name, self._error = name, error

    def check(self) -> str:
        if self._error:
            raise ProbeFailedError(self._error)
        return "fine"
```

`Probe` is the test double. Its constructor takes a `name` and an optional `error` text (`str | None` means "text or nothing", default `None`). `self.name, self._error = name, error` stores both; the leading underscore on `_error` is a convention for "internal, do not touch from outside". The `check` method raises `ProbeFailedError` with the stored text if one was given, and otherwise returns the word `fine`. `if self._error:` is true for any non-empty text.

`tests/unit/application/test_health.py`, lines 14 to 17:

```python
def test_all_probes_passing_is_healthy():
    report = check_health([Probe("a"), Probe("b")])
    assert report.healthy
    assert [r.detail for r in report.results] == ["fine", "fine"]
```

With two passing probes the report must be healthy. The second `assert` uses a **list comprehension**, `[r.detail for r in report.results]`, which builds a list by taking the `detail` of every result, and compares it with `["fine", "fine"]`.

`tests/unit/application/test_health.py`, lines 20 to 23:

```python
def test_one_failing_probe_is_reported_and_makes_the_report_unhealthy():
    report = check_health([Probe("a"), Probe("b", "down")])
    assert not report.healthy
    assert [(r.name, r.ok, r.detail) for r in report.results] == [("a", True, "fine"), ("b", False, "down")]
```

With one failing probe, the report must not be healthy and must still contain both results in order. The comprehension here builds one tuple per result, `(r.name, r.ok, r.detail)`, and the expected list shows that probe `a` passed with `fine` and probe `b` failed with the message `down`. That the second result exists at all proves the failing probe did not stop the loop.

#### `tests/unit/infrastructure/test_logging_and_shutdown.py`

Two helpers are tested here. `configure_logging` makes every log record come out as one line of **logfmt**, a plain-text format of `key=value` pairs separated by spaces. `ShutdownSignal` is a flag that Ctrl-C (the `SIGINT` signal) or `SIGTERM` sets, so a long loop can notice the request and stop cleanly between two units of work. A **signal** is a small message the operating system sends to a running program; `SIGINT` is what Ctrl-C sends and `SIGTERM` is what `kill` and `docker stop` send by default.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 1 to 6:

```python
import io
import logging
import signal

from slow_queries.infrastructure.logging import configure_logging, fields
from slow_queries.infrastructure.shutdown import ShutdownSignal
```

`io` is the standard library module for streams; `io.StringIO` is a fake file that keeps its text in memory. `logging` is the standard logging module. `signal` gives access to operating-system signals. The last two imports bring in the lab's helpers: `configure_logging` and `fields` (which attaches key and value pairs to a log call), and the `ShutdownSignal` class.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 9 to 19:

```python
def test_a_record_becomes_one_logfmt_line_with_its_fields():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("demo").info("partitions assigned", extra=fields(member="consumer-1", partitions=[0, 1]))
    line = stream.getvalue().strip()
    assert line.startswith("ts=")
    assert "level=INFO" in line
    assert "logger=demo" in line
    assert 'msg="partitions assigned"' in line
    assert "member=consumer-1" in line
    assert 'partitions="[0, 1]"' in line
```

The first test follows one log call from start to finish. `stream = io.StringIO()` is a text buffer standing in for the terminal. `configure_logging("INFO", stream)` tells the logging system to show records of level `INFO` and above and to write them to that buffer in logfmt. `logging.getLogger("demo")` returns the logger named `demo`; `.info("partitions assigned", extra=fields(member="consumer-1", partitions=[0, 1]))` writes one record with extra pairs. `stream.getvalue().strip()` reads everything written so far and removes the trailing newline. The asserts check each piece of the line: it starts with `ts=` (the timestamp), contains `level=INFO` and `logger=demo`, the message in quotes because it contains a space (`msg="partitions assigned"`), the plain pair `member=consumer-1`, and the list shown as text in quotes (`partitions="[0, 1]"`) because its text contains a space.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 22 to 26:

```python
def test_records_below_the_level_are_dropped_():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("demo").debug("hidden")
    assert stream.getvalue() == ""
```

A `DEBUG` message is less important than the `INFO` threshold, so it must be dropped: the buffer must still be an empty string.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 29 to 37:

```python
def test_an_exception_is_attached_to_the_line():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    try:
        raise ValueError("boom")
    except ValueError:
        logging.getLogger("demo").exception("failed")
    assert "exc=" in stream.getvalue()
    assert "boom" in stream.getvalue()
```

When code logs from inside an `except` block with `.exception(...)`, the log line has to carry the error. The test raises a `ValueError` on purpose inside `try:`, catches it with `except ValueError:`, and logs there. It then checks that the line has an `exc=` pair and that the word `boom`, the error's message, appears in it.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 40 to 45:

```python
def test_configuring_twice_does_not_duplicate_lines():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    configure_logging("INFO", stream)
    logging.getLogger("demo").info("once")
    assert stream.getvalue().count("msg=once") == 1
```

Calling `configure_logging` twice must not make every message appear twice. The helper replaces the list of handlers on the root logger (a **handler** is the part of the logging system that sends a record somewhere), and this test proves it: after two calls one `info("once")` produces exactly one `msg=once`, counted with the string method `.count(...)`.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 48 to 52:

```python
def test_a_shutdown_signal_starts_unset_and_is_set_by_request():
    shutdown = ShutdownSignal()
    assert not shutdown.requested
    shutdown.request()
    assert shutdown.requested
```

A new `ShutdownSignal` starts with its flag down (`requested` is false) and `request()` raises it. The class stores the flag in a `threading.Event`, a thread-safe on/off switch, and this test checks the public behavior without caring how it is stored.

`tests/unit/infrastructure/test_logging_and_shutdown.py`, lines 55 to 64:

```python
def test_sigterm_sets_the_flag_once_installed():
    shutdown = ShutdownSignal()
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        shutdown.install()
        signal.raise_signal(signal.SIGTERM)
        assert shutdown.requested
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
```

The last test sends a real signal to the test process. `signal.getsignal(number)` returns whatever function currently handles that signal; the dictionary comprehension saves the handlers for `SIGINT` and `SIGTERM` in `previous`, because the test is about to replace them and must put them back so that it does not disturb the other tests or pytest itself. `shutdown.install()` registers the helper's handler for both signals. `signal.raise_signal(signal.SIGTERM)` makes the process send itself a `SIGTERM`; the handler runs and sets the flag, so `assert shutdown.requested` passes. The `finally:` block runs whether or not the assert passed, and the loop in it calls `signal.signal(number, handler)` to restore every saved handler.

### The remaining unit tests of this repository, line by line

These are the unit test files that belong to this repository alone. Each one is quoted completely and then explained. A reminder of two pytest features used below. **`pytest.raises(SomeError, match="text")`** is a block that passes only if the code inside raises that error and the error's message contains the given text (the `match` value is a regular expression searched in the message). **`@pytest.mark.parametrize("name", [a, b, c])`** placed above a test function runs that function once for each listed value, giving the value to the argument called `name`; each run is reported as its own test.

#### `tests/unit/domain/test_plan.py`

The code under test turns the text that PostgreSQL prints for `EXPLAIN (ANALYZE, BUFFERS)` into a small summary object: the execution time, the number of 8 kilobyte pages touched, the kinds of plan step (called nodes), the indexes used, how many rows a filter threw away and how many times an index-only scan had to visit the table anyway (heap fetches). The tests feed it plan text written out by hand, so no database is needed.

`tests/unit/domain/test_plan.py`, lines 1 to 4:

```python
import pytest

from slow_queries.domain.errors import PlanParseError
from slow_queries.domain.plan import pages_touched, parse_json_plan, parse_text_plan
```

`pytest` is needed for `pytest.raises`. The next line imports the error class `PlanParseError`, which the parser raises for text it cannot read. The last line imports the three functions under test: `pages_touched`, `parse_json_plan` and `parse_text_plan`.

`tests/unit/domain/test_plan.py`, lines 6 to 13:

```python
SEQ_SCAN = [
    "Seq Scan on orders  (cost=0.00..78125.01 rows=5000 width=456) (actual time=1.1..384.2 rows=2748.00 loops=1)",
    "  Filter: (date(created_at) = '2026-03-14'::date)",
    "  Rows Removed by Filter: 997252",
    "  Buffers: shared hit=47646 read=15479 written=158",
    "Planning Time: 0.042 ms",
    "Execution Time: 384.711 ms",
]
```

`SEQ_SCAN` is a list of text lines in exactly the shape PostgreSQL prints for a query that read the whole `orders` table (`Seq Scan` means sequential scan). The module-level name in capital letters is a Python convention for a constant. Reading the lines one by one: line 7 is the plan node with its estimates (`cost`, `rows`, `width`) and, in the second pair of parentheses, what really happened (`actual time` in milliseconds, `rows`, `loops`). Line 8 is the filter, which keeps only rows of one date. Line 9 says 997,252 rows were read and thrown away. Line 10 is the buffer line: `shared hit=47646` pages were found in PostgreSQL's memory cache, `read=15479` had to be fetched from the operating system, and `written=158` were written out. Line 11 is the time spent planning. Line 12 is the total execution time, which is the line the parser looks for first.

`tests/unit/domain/test_plan.py`, lines 14 to 20:

```python
INDEX_ONLY = [
    "Index Only Scan using idx_orders_listing on orders  (cost=0.42..50.02 rows=960 width=33) (actual rows=1010.00)",
    "  Heap Fetches: 0",
    "  Buffers: shared hit=506",
    "Serialization: time=0.896 ms  output=69kB  format=text",
    "Execution Time: 2.095 ms",
]
```

`INDEX_ONLY` is the plan of a query answered from an index alone. Its node line says `Index Only Scan using idx_orders_listing`, so the index name is part of the node text. `Heap Fetches: 0` says that the table itself never had to be visited, which only works when the table's pages are marked all-visible. `Buffers: shared hit=506` is the page count. The `Serialization:` line is something PostgreSQL 17 and later print when the `SERIALIZE` option is used: the time spent turning the result rows into the text sent to the client.

`tests/unit/domain/test_plan.py`, lines 21 to 27:

```python
SORT_OVER_BITMAP = [
    "Sort  (cost=3710.69..3713.21 rows=1006 width=457) (actual time=2.4..2.5 rows=1010.00 loops=1)",
    "  Buffers: shared hit=1009",
    "  ->  Bitmap Heap Scan on orders  (cost=29.48..3722.78 rows=1024 width=457) (actual time=0.1..1.9 rows=1010)",
    "        ->  Bitmap Index Scan on idx_orders_customer_created  (cost=0.00..29.23 rows=1024 width=0)",
    "Execution Time: 3.293 ms",
]
```

`SORT_OVER_BITMAP` has three nested nodes: a `Sort` on top, a `Bitmap Heap Scan` below it and a `Bitmap Index Scan` below that. The arrow `->` and the deeper indentation mark nesting. A bitmap scan first collects the locations of matching rows from an index into an in-memory bitmap and then reads the table pages in physical order. Its index name appears as `Bitmap Index Scan on idx_orders_customer_created`, a different wording from the `using` of the other scans.

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

The first test parses the sequential scan and checks every field of the summary. `plan.execution_ms == 384.711` is the number from the last line. `plan.pages == 47646 + 15479` shows how pages are counted: `hit` plus `read`, and not `written`. `node_types == ("Seq Scan",)` compares with a one-item tuple. `rows_removed_by_filter == 997252` is the number from the filter line. `plan.heap_fetches is None` uses `is None` because the plan has no such line, so the value is "not reported" rather than zero. `plan.has_node("Seq Scan")` is true and `not plan.has_node("Sort")` is true, which tests the helper that looks a node type up.

`tests/unit/domain/test_plan.py`, lines 41 to 46:

```python
def test_an_index_only_scan_reports_the_index_and_zero_heap_fetches():
    plan = parse_text_plan(INDEX_ONLY)
    assert plan.index_names == ("idx_orders_listing",)
    assert plan.heap_fetches == 0
    assert plan.uses_index("idx_orders_listing")
    assert not plan.uses_index("orders_pkey")
```

The second test reads the index-only plan. `plan.index_names == ("idx_orders_listing",)` shows that the name was cut out of the `using` text. `heap_fetches == 0` is the "zero" case, which is different from `None`: a zero tells the reader the index-only scan was fully effective. `uses_index` answers yes for the name that appears and no for `orders_pkey`, which does not.

`tests/unit/domain/test_plan.py`, lines 49 to 52:

```python
def test_nested_nodes_and_bitmap_index_names_are_found():
    plan = parse_text_plan(SORT_OVER_BITMAP)
    assert plan.node_types == ("Sort", "Bitmap Heap Scan", "Bitmap Index Scan")
    assert plan.index_names == ("idx_orders_customer_created",)
```

The third test checks that indentation does not confuse the parser. The nodes must come back in the order they appear, outermost first, and the index name of the bitmap node must be found too.

`tests/unit/domain/test_plan.py`, lines 55 to 62:

```python
def test_pages_after_serialization_are_added_to_the_top_nodes_pages():
    lines = [
        "Seq Scan on t  (cost=0..1 rows=1)",
        "  Buffers: shared hit=207",
        "Serialization: time=30 ms",
        "  Buffers: shared hit=10625",
    ]
    assert pages_touched(lines) == 207 + 10625
```

The fourth test covers a detail of PostgreSQL 18: after the `Serialization:` line there can be a second `Buffers:` line for the pages touched while preparing the output (for example, reading oversized values stored out of line). The test builds a small plan inline with two buffer lines, 207 pages for the scan and 10,625 for serialization, and checks that `pages_touched` adds them. Writing the list inside the test instead of at the top of the file keeps the odd input next to the one assertion that needs it.

`tests/unit/domain/test_plan.py`, lines 65 to 67:

```python
def test_a_plan_without_analyze_is_refused():
    with pytest.raises(PlanParseError, match="Execution Time"):
        parse_text_plan(["Seq Scan on orders  (cost=0.00..1.00 rows=1 width=1)"])
```

A plan printed without `ANALYZE` has estimates but no execution time. The parser must refuse it rather than invent a zero, because a made-up number would look like a measurement. The test passes a one-line plan and checks that `PlanParseError` is raised with a message that mentions `Execution Time`.

`tests/unit/domain/test_plan.py`, lines 70 to 86:

```python
def test_json_plans_give_the_same_summary():
    document = {
        "Execution Time": 4.0,
        "Plan": {
            "Node Type": "Limit",
            "Shared Hit Blocks": 10,
            "Shared Read Blocks": 3,
            "Plans": [
                {"Node Type": "Index Scan", "Index Name": "idx_orders_customer_created", "Rows Removed by Filter": 7}
            ],
        },
    }
    plan = parse_json_plan(document)
    assert (plan.execution_ms, plan.pages) == (4.0, 13)
    assert plan.node_types == ("Limit", "Index Scan")
    assert plan.index_names == ("idx_orders_customer_created",)
    assert plan.rows_removed_by_filter == 7
```

The same plan can be printed as JSON (`EXPLAIN (FORMAT JSON)`), in which each node is a dictionary with keys like `"Node Type"`, `"Shared Hit Blocks"` and a list under `"Plans"` for its children. `document` is a hand-written dictionary of that shape: a `Limit` node with a child `Index Scan`. `Shared Hit Blocks` 10 and `Shared Read Blocks` 3 give 13 pages. The test checks that the JSON parser gives the same summary as the text parser would: time 4.0 and pages 13 compared as a pair, node types `("Limit", "Index Scan")` in tree order, the index name, and the filter count 7 found on the child node.

`tests/unit/domain/test_plan.py`, lines 89 to 94:

```python
def test_json_heap_fetches_are_reported():
    document = {
        "Execution Time": 1.0,
        "Plan": {"Node Type": "Index Only Scan", "Shared Hit Blocks": 1, "Shared Read Blocks": 0, "Heap Fetches": 0},
    }
    assert parse_json_plan(document).heap_fetches == 0
```

JSON plans report heap fetches under the key `"Heap Fetches"`. This test builds an index-only scan with value 0 and checks that zero comes through, not `None`.

`tests/unit/domain/test_plan.py`, lines 97 to 99:

```python
def test_a_json_plan_with_the_wrong_shape_is_refused():
    with pytest.raises(PlanParseError, match="unexpected JSON plan shape"):
        parse_json_plan({"Plan": {}})
```

A document without the `"Execution Time"` key does not have the shape of an `EXPLAIN` result. The parser must raise `PlanParseError` with the message `unexpected JSON plan shape`, so that a mistake in how the plan was fetched is reported clearly instead of showing up later as a missing-key error.

#### `tests/unit/domain/test_write_cost.py`

This is about the price of an index. Every extra index must be updated on each `INSERT`, so the lab measures a batch of inserts with `EXPLAIN (ANALYZE, BUFFERS, WAL)` and parses three figures from it: the time, the pages touched and the amount of **write-ahead log** (WAL) produced. The WAL is the file in which PostgreSQL writes down every change before applying it, so that it can recover after a crash.

`tests/unit/domain/test_write_cost.py`, lines 1 to 4:

```python
import pytest

from slow_queries.domain.errors import PlanParseError
from slow_queries.domain.write_cost import WriteCost, median_cost, parse_write_cost
```

Imports `pytest`, the parse error, and the three names under test: the `WriteCost` value object, `median_cost` and `parse_write_cost`.

`tests/unit/domain/test_write_cost.py`, lines 6 to 11:

```python
INSERT_PLAN = [
    "Insert on orders  (cost=0.00..1.00 rows=0 width=0) (actual time=40.1..40.1 rows=0.00 loops=1)",
    "  Buffers: shared hit=31412 dirtied=2000",
    "  WAL: records=20330 fpi=10 bytes=5900000",
    "Execution Time: 41.8 ms",
]
```

`INSERT_PLAN` is what an `EXPLAIN` of an `INSERT` prints. The `WAL:` line has three fields: `records=20330` log records written, `fpi=10` full-page images (whole 8 kilobyte pages copied into the log the first time a page changes after a checkpoint) and `bytes=5900000`. `dirtied=2000` on the buffer line counts pages changed in memory.

`tests/unit/domain/test_write_cost.py`, lines 14 to 15:

```python
def test_an_insert_plan_gives_time_pages_and_wal():
    assert parse_write_cost(INSERT_PLAN) == WriteCost(41.8, 31412, 20330, 5_900_000)
```

The parser must return a `WriteCost` equal to the one built by hand from the numbers 41.8 milliseconds, 31412 pages, 20330 WAL records and 5,900,000 WAL bytes. Python lets you write the number `5_900_000` with underscores to make it readable. Comparing two dataclass objects with `==` compares all their fields, so the single assert checks four numbers.

`tests/unit/domain/test_write_cost.py`, lines 18 to 20:

```python
def test_a_plan_without_wal_is_refused():
    with pytest.raises(PlanParseError, match="WAL"):
        parse_write_cost(["Insert on orders", "Execution Time: 1.0 ms"])
```

A plan with no `WAL:` line (for example, one captured without the `WAL` option) cannot give the write cost. The parser must raise `PlanParseError` naming `WAL`.

`tests/unit/domain/test_write_cost.py`, lines 23 to 25:

```python
def test_the_median_is_taken_per_figure():
    samples = [WriteCost(10, 100, 1000, 5000), WriteCost(30, 300, 3000, 9000), WriteCost(20, 200, 2000, 7000)]
    assert median_cost(samples) == WriteCost(20, 200, 2000, 7000)
```

The lab repeats each measurement and keeps the **median**: the middle value once the values are sorted. A median is not thrown off by one slow outlier the way an average is. The three samples are deliberately given out of order (10, 30, 20), and each of the four figures has its own middle: 20, 200, 2000 and 7000. The test proves the median is taken separately for each figure and not by picking one whole sample.

`tests/unit/domain/test_write_cost.py`, lines 28 to 30:

```python
def test_the_median_of_nothing_is_an_error():
    with pytest.raises(ValueError, match="at least one"):
        median_cost([])
```

The median of an empty list does not exist. The function must raise `ValueError` with a message containing `at least one`, instead of failing later with an obscure index error.

#### `tests/unit/domain/test_comparison_and_lesson.py`

`tests/unit/domain/test_comparison_and_lesson.py`, lines 1 to 7:

```python
from slow_queries.domain import lesson
from slow_queries.domain.comparison import Improvement
from slow_queries.domain.plan import PlanSummary


def plan(ms: float, pages: int) -> PlanSummary:
    return PlanSummary(ms, pages, (), (), 0, None)
```

The imports bring in the lesson data module, `Improvement` (a before-and-after pair of plans) and `PlanSummary`. The helper `plan(ms, pages)` builds a summary with only the two interesting numbers set: the remaining fields are an empty node list, an empty index list, zero filtered rows and no heap-fetch count. A small helper like this keeps the tests below to one line per plan.

`tests/unit/domain/test_comparison_and_lesson.py`, lines 10 to 13:

```python
def test_speedup_and_pages_ratio_compare_before_with_after():
    improvement = Improvement(plan(400.0, 60000), plan(4.0, 3000))
    assert improvement.speedup == 100.0
    assert improvement.pages_ratio == 20.0
```

A query that took 400 ms and touched 60,000 pages before, and 4 ms and 3,000 pages after, is 100 times faster and touches 20 times fewer pages. The two assertions check the two ratios. The test uses `==` on floating-point numbers; that is safe here because 400.0 / 4.0 and 60000 / 3000 are exactly representable.

`tests/unit/domain/test_comparison_and_lesson.py`, lines 16 to 19:

```python
def test_a_zero_millisecond_result_does_not_divide_by_zero():
    improvement = Improvement(plan(1.0, 10), plan(0.0, 0))
    assert improvement.speedup == 1000.0
    assert improvement.pages_ratio == 10.0
```

If the new plan took 0.0 ms, dividing would fail. The code treats zero as 0.001 ms (and zero pages as one page), so a 1.0 ms query becomes "1000 times faster" and 10 pages over one page is 10. The test pins both fallbacks.

`tests/unit/domain/test_comparison_and_lesson.py`, lines 22 to 27:

```python
def test_every_comparison_names_plans_the_replay_captures():
    captured = set(lesson.BEFORE_ANY_INDEX)
    for step in lesson.STEPS:
        captured |= set(step.captures)
    for _label, before, after in lesson.COMPARISONS:
        assert {before, after} <= captured
```

The lesson is described as data: a tuple of steps and a table of comparisons, each naming two plans by label. This test guards against a typo in a label. It builds the set of every plan the replay will capture (the plans taken before any index, plus the ones named by each step; `|=` adds the elements of one set to another), then for each comparison row checks that both of its plan names are in that set. `{before, after} <= captured` builds a two-element set and tests that it is a subset. `for _label, before, after in ...` unpacks each three-item row, and the leading underscore marks the label as unused.

`tests/unit/domain/test_comparison_and_lesson.py`, lines 30 to 31:

```python
def test_the_steps_are_numbered_from_one_without_gaps():
    assert [step.number for step in lesson.STEPS] == [1, 2, 3, 4]
```

The migrations are files numbered 1 to 4. The steps must be numbered the same way with no gap, so the test compares the list of step numbers with `[1, 2, 3, 4]`.

#### `tests/unit/infrastructure/test_sql_script.py`

PostgreSQL's driver can run only one statement at a time, but the lab's `.sql` files contain several. `split_statements` cuts a script into single statements. It must not cut at a semicolon inside a comment or inside quotes, and it must drop lines that belong to the `psql` program rather than to SQL (lines starting with a backslash).

`tests/unit/infrastructure/test_sql_script.py`, lines 1 to 5:

```python
from slow_queries.infrastructure.sql_script import split_statements


def test_statements_are_split_on_semicolons():
    assert split_statements("SELECT 1; SELECT 2;") == ["SELECT 1", "SELECT 2"]
```

The function under test and the simplest case: two statements separated by semicolons come back as two strings without their semicolons.

`tests/unit/infrastructure/test_sql_script.py`, lines 8 to 9:

```python
def test_comments_are_dropped_even_with_a_semicolon_in_them():
    assert split_statements("-- one; two\nSELECT 1; -- trailing; note\nSELECT 2;") == ["SELECT 1", "SELECT 2"]
```

SQL comments start with two hyphens and run to the end of the line. The first comment contains a semicolon (`-- one; two`), the second comes after a statement (`-- trailing; note`). Neither may split anything and neither may appear in the result. In the Python string `\n` is a line break.

`tests/unit/infrastructure/test_sql_script.py`, lines 12 to 13:

```python
def test_a_semicolon_inside_quotes_does_not_split():
    assert split_statements("SELECT 'a;b'; SELECT \"c;d\";") == ["SELECT 'a;b'", 'SELECT "c;d"']
```

A semicolon inside single quotes (a text value) or double quotes (an identifier) is part of the text. The Python string uses `\"` to put a double quote inside a double-quoted Python string; the expected list uses single quotes around the second item for the same reason.

`tests/unit/infrastructure/test_sql_script.py`, lines 16 to 17:

```python
def test_psql_meta_commands_are_not_sql():
    assert split_statements("\\set rows 5\nSELECT 1;\n\\gset\n") == ["SELECT 1"]
```

Lines like `\set rows 5` and `\gset` are commands of the `psql` program, not SQL. A driver would send them to the server and get a syntax error, so they must vanish. In Python source `"\\set"` is the way to write one real backslash.

`tests/unit/infrastructure/test_sql_script.py`, lines 20 to 21:

```python
def test_text_after_the_last_semicolon_is_ignored_like_an_empty_statement():
    assert split_statements("SELECT 1;\n  \n") == ["SELECT 1"]
```

Whitespace after the last semicolon is not a statement. The result is just the one real statement.

`tests/unit/infrastructure/test_sql_script.py`, lines 24 to 31:

```python
def test_every_repository_sql_file_that_python_runs_splits_into_complete_statements():
    import pathlib

    sql = pathlib.Path(__file__).resolve().parents[3] / "sql"
    for path in [*sorted((sql / "migrations").rglob("*.sql")), *sorted((sql / "explain").glob("*.sql"))]:
        statements = split_statements(path.read_text())
        assert statements, path.name
        assert all(not statement.endswith(";") for statement in statements)
```

The last test runs the splitter on the repository's real files. `pathlib.Path(__file__).resolve().parents[3] / "sql"` finds the `sql` folder: `__file__` is this test file, `.resolve()` makes it an absolute path, `.parents[3]` goes up four levels (the folders `infrastructure`, `unit`, `tests`, then the repository root; the index starts at zero for the immediate parent), and `/ "sql"` appends a folder name. The loop visits every file under `sql/migrations` (searched recursively with `rglob`) and every file in `sql/explain`, in sorted order so failures are reproducible. For each, `assert statements, path.name` demands at least one statement, and gives the file name as the failure message. The last line checks with `all(...)` that no statement ends with a semicolon, which would show that the splitter left one behind.

#### `tests/unit/application/test_replay.py`

The code under test, `ReplayLesson`, is the heart of the lab: it resets the database, applies the four index migrations one at a time, captures the plans, measures write costs and saves everything. The test supplies the fakes from `fakes.py` (a `FakeDatabase` that records each call, and a `RecordingStore`), so the order of steps can be checked without PostgreSQL.

`tests/unit/application/test_replay.py`, lines 1 to 14:

```python
import pytest

from slow_queries.application.replay import ReplayLesson
from slow_queries.domain import lesson
from slow_queries.domain.errors import LessonInterruptedError

from .fakes import FakeDatabase, RecordingStore


def run(database: FakeDatabase | None = None, **options):
    database = database or FakeDatabase()
    store = RecordingStore()
    result = ReplayLesson(database, store, **options).run()
    return database, store, result
```

`from .fakes import ...` is a relative import: the dot means "the module next to this one". The helper `run` creates a fake database (or uses one given), a recording store, runs the replay with any extra options passed through `**options` (all the keyword arguments collected into a dictionary and handed on), and returns the three things tests want to look at. `database or FakeDatabase()` uses the given database, or makes a new one if `None` was given.

`tests/unit/application/test_replay.py`, lines 17 to 19:

```python
def test_the_lesson_starts_from_the_primary_key_alone():
    database, _store, _result = run()
    assert database.calls[0] == "reset_to 0"
```

The first recorded call must be `reset_to 0`: the lesson starts from a table that has only its primary key index.

`tests/unit/application/test_replay.py`, lines 22 to 26:

```python
def test_plans_before_any_index_are_read_before_the_first_migration():
    database, _store, _result = run()
    first_step = database.calls.index("apply_step 1")
    captured_before = [call for call in database.calls[:first_step] if call.startswith("capture")]
    assert captured_before == [f"capture {name}" for name in lesson.BEFORE_ANY_INDEX]
```

`database.calls.index("apply_step 1")` gives the position of the first migration call. The slice `calls[:first_step]` is everything before it. The list comprehension keeps only the calls that start with `capture`, and these must equal the plans in `lesson.BEFORE_ANY_INDEX` in order. This protects the point of the lesson: the "before" plans must be read before any index exists.

`tests/unit/application/test_replay.py`, lines 29 to 39:

```python
def test_each_step_is_applied_then_read_then_costed_then_vacuumed_in_order():
    database, _store, _result = run()
    assert database.calls[database.calls.index("apply_step 2") :][:7] == [
        "apply_step 2",
        "capture q2_latest_whale_after",
        "capture q2_latest_small_after",
        "capture q3_listing_before",
        "capture q3_listing_narrow",
        "measure 5",
        "vacuum",
    ]
```

After step 2 is applied, exactly this sequence must follow: the four captures that step names, then `measure 5` (a write-cost measurement with the default five repetitions) and `vacuum`. `calls[calls.index("apply_step 2") :][:7]` means "from the position of that call to the end, then keep the first seven". The space before the colon is the formatter's style for a slice with a complex start.

`tests/unit/application/test_replay.py`, lines 42 to 46:

```python
def test_every_plan_is_saved_and_summarized():
    _database, store, result = run()
    expected = set(lesson.BEFORE_ANY_INDEX) | {name for step in lesson.STEPS for name in step.captures}
    assert set(store.plans) == expected == set(result.plans)
    assert result.plans["q1_day_before"].execution_ms == 10.0
```

Every plan the lesson names must be both saved to the store and present in the result. The `expected` set joins the pre-index plans and, with a set comprehension, every capture of every step. The chained comparison `a == expected == b` demands all three sets to be equal. `execution_ms == 10.0` holds because the fake's plan text says `Execution Time: 10.0 ms`.

`tests/unit/application/test_replay.py`, lines 49 to 53:

```python
def test_the_write_cost_of_each_index_set_is_recorded_including_the_empty_set():
    _database, _store, result = run(repetitions=3)
    labels = [label for label, _cost in result.write_costs]
    assert labels[0] == "no new indexes"
    assert labels[1:] == [step.label for step in lesson.STEPS]
```

Write costs are recorded for the empty set of new indexes first, then after each step. The result holds pairs of (label, cost); the comprehension keeps just the labels. `labels[1:]` is the list without its first item. `repetitions=3` passes through `run`'s options.

`tests/unit/application/test_replay.py`, lines 56 to 59:

```python
def test_the_notes_are_saved_once_at_the_end():
    _database, store, _result = run()
    assert store.report is not None
    assert store.report.startswith("# Results of the last")
```

The notes file is produced once at the end. `store.report is not None` means it was saved, and `startswith("# Results of the last")` checks the title line of the Markdown.

`tests/unit/application/test_replay.py`, lines 62 to 64:

```python
def test_a_changed_row_count_means_a_write_batch_was_not_rolled_back():
    with pytest.raises(AssertionError, match="rolled back"):
        run(FakeDatabase(rows=1000, rows_after=1500))
```

Every write-cost batch runs inside a transaction that is rolled back, so the table's row count must be the same before and after. The fake is built with 1000 rows the first time the count is read and 1500 afterwards, which imitates a batch that was accidentally committed. The replay must stop with an `AssertionError` whose message mentions `rolled back`.

`tests/unit/application/test_replay.py`, lines 67 to 77:

```python
def test_a_stop_request_ends_the_replay_between_steps_without_saving_notes():
    database, store, calls = FakeDatabase(), RecordingStore(), []

    def should_stop() -> bool:
        calls.append(1)
        return len(calls) > 8

    with pytest.raises(LessonInterruptedError):
        ReplayLesson(database, store, should_stop=should_stop).run()
    assert store.report is None
    assert "apply_step 4" not in database.calls
```

This test checks Ctrl-C handling. `should_stop` is a function defined inside the test that appends to a list each time it is asked and answers yes after the eighth question. The replay asks between steps, so it should raise `LessonInterruptedError` partway through. Two checks follow: `store.report is None` (no half-finished notes were saved) and `"apply_step 4"` is not among the recorded calls (it really stopped early). Because `should_stop` is passed to `ReplayLesson` directly, the test needs no real signal.

`tests/unit/application/test_replay.py`, lines 80 to 84:

```python
def test_progress_is_reported_for_each_step_and_plan():
    messages: list[str] = []
    run(progress=messages.append)
    assert "step 1: + idx_orders_created_at" in messages
    assert any(message.startswith("plan q1_day_before") for message in messages)
```

The replay reports its progress through a callback. `progress=messages.append` collects the messages in a list. The test checks one exact message for step 1 and, with `any(...)` over a generator expression, that at least one message starts with `plan q1_day_before`.

#### `tests/unit/application/test_report.py`

The code under test, `render_results`, turns a `LessonResult` into the Markdown text of `results.md`. These tests look for exact lines of that text.

`tests/unit/application/test_report.py`, lines 1 to 13:

```python
from slow_queries.application.replay import LessonResult
from slow_queries.application.report import render_results
from slow_queries.domain import lesson
from slow_queries.domain.plan import PlanSummary
from slow_queries.domain.write_cost import WriteCost


def result() -> LessonResult:
    plans = {}
    for name in [*lesson.BEFORE_ANY_INDEX, *(n for step in lesson.STEPS for n in step.captures)]:
        slow = name.endswith(("before", "wide"))
        plans[name] = PlanSummary(400.0 if slow else 4.0, 60000 if slow else 3000, (), (), 0, None)
    return LessonResult(plans, (("no new indexes", WriteCost(42.5, 31000, 20000, 5_900_000)),), {"idx_a": 22_500_000})
```

`result()` builds a result by hand. It loops over the names of every plan, the ones before any index and, using a generator expression, those of every step. A name that ends with `before` or `wide` (`name.endswith(("before", "wide"))` accepts a tuple of endings) is a slow query: 400 ms and 60,000 pages. The others get 4 ms and 3,000 pages. `PlanSummary(...)` is filled positionally: time, pages, no node types, no indexes, zero removed rows and no heap-fetch count. The `LessonResult` has three parts: the plans, one write-cost row labelled `no new indexes`, and a dictionary of index sizes in bytes.

`tests/unit/application/test_report.py`, lines 16 to 18:

```python
def test_the_comparison_table_has_a_row_per_query_with_the_speedup():
    text = render_results(result())
    assert "| q1 day query | 400.000 | 4.000 | 100x | 60000 | 3000 |" in text
```

The comparison table has one row per query with the label, the before and after milliseconds, the speedup and the pages. `400.000 / 4.000` gives `100x`.

`tests/unit/application/test_report.py`, lines 21 to 24:

```python
def test_the_write_cost_table_and_index_sizes_follow():
    text = render_results(result())
    assert "| no new indexes | 42.5 | 31000 | 20000 | 5.9 |" in text
    assert "| idx_a | 22.5 |" in text
```

The write-cost table prints bytes of WAL as megabytes with one decimal (5,900,000 bytes appear as `5.9`) and the index sizes as megabytes too (22,500,000 bytes appear as `22.5`).

`tests/unit/application/test_report.py`, lines 27 to 34:

```python
def test_the_host_load_note_is_printed_when_it_is_known():
    from dataclasses import replace

    from slow_queries.domain.host import HostLoad

    text = render_results(replace(result(), host_load=HostLoad(40.0, 12)))
    assert "Measured on a loaded machine (load average 40.0 on 12 CPUs)" in text
    assert "Measured" not in render_results(result())
```

When a `HostLoad` is attached, the notes must say so. `dataclasses.replace(result(), host_load=...)` makes a copy of the result with one field changed, which works because the result is a frozen dataclass that cannot be modified in place. The imports sit inside the function because only this test uses them. The last assertion checks the other case: without a load the word `Measured` appears nowhere.

#### `tests/unit/infrastructure/test_settings.py`

`Settings.from_env` reads configuration from a dictionary of environment variables (the named values a program receives from the shell that starts it). Tests pass a dictionary instead of the real environment, which makes them independent of the machine they run on.

`tests/unit/infrastructure/test_settings.py`, lines 1 to 5:

```python
import pytest

from slow_queries.infrastructure.settings import ConfigurationError, Settings

MINIMAL = {"PGPASSWORD": "s3cret-value"}
```

`MINIMAL` is the one variable that has no default: the database password. The value `s3cret-value` is a harmless made-up string used to check that it never leaks.

`tests/unit/infrastructure/test_settings.py`, lines 8 to 15:

```python
def test_defaults_describe_the_local_compose_setup():
    settings = Settings.from_env(MINIMAL)
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("localhost", 55431, "lab", "lab")
    assert (postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == (5, 120_000)
    assert postgres.max_parallel_workers_per_gather == 0
    assert settings.log_level == "INFO"
    assert settings.sql_dir.name == "sql"
```

With only the password given, every other setting takes its default: host `localhost`, port `55431` (the lab's database is published on this port so that it does not clash with a PostgreSQL already on 5432), database and user `lab`, a 5 second connect timeout, a statement timeout of 120,000 ms (two minutes), zero parallel workers per gather, log level `INFO`, and a `sql` folder.

`tests/unit/infrastructure/test_settings.py`, lines 18 to 20:

```python
def test_the_database_password_has_no_default():
    with pytest.raises(ConfigurationError, match="PGPASSWORD"):
        Settings.from_env({})
```

With no variables at all, building the settings must fail with a `ConfigurationError` that names `PGPASSWORD`.

`tests/unit/infrastructure/test_settings.py`, lines 23 to 24:

```python
def test_the_password_never_appears_in_a_printed_settings_object():
    assert "s3cret-value" not in repr(Settings.from_env(MINIMAL))
```

`repr(...)` is the text Python shows when an object is printed in a log or an error report. The password field is marked to stay out of it, and the test proves that the string does not contain the password.

`tests/unit/infrastructure/test_settings.py`, lines 27 to 46:

```python
def test_every_variable_can_be_overridden():
    settings = Settings.from_env(
        {
            **MINIMAL,
            "PGHOST": "db",
            "PGPORT": "6543",
            "PGDATABASE": "x",
            "PGUSER": "u",
            "PG_CONNECT_TIMEOUT_SECONDS": "2",
            "PG_STATEMENT_TIMEOUT_MS": "500",
            "PG_PARALLEL_WORKERS_PER_GATHER": "2",
            "LAB_SQL_DIR": "/somewhere/sql",
            "LOG_LEVEL": "debug",
        }
    )
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("db", 6543, "x", "u")
    assert (postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == (2, 500)
    assert postgres.max_parallel_workers_per_gather == 2
    assert (postgres.password, settings.log_level, str(settings.sql_dir)) == ("s3cret-value", "DEBUG", "/somewhere/sql")
```

Every variable can be overridden. `**MINIMAL` inside the dictionary copies the password entry in. The values are all strings, because environment variables are always text; the settings code converts them to numbers. The checks compare tuples of fields at once: host `db`, port `6543` (a number now), database `x`, user `u`, timeouts 2 seconds and 500 ms, two workers, and finally the password, the log level `DEBUG` (the input `debug` is turned into upper case) and the folder.

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

This parametrized test runs once for each bad input: a port of `0` or `five`, a host of only spaces, a negative timeout or worker count, and a log level that does not exist. Each time the settings must raise `ConfigurationError` and the message must contain the name of the offending variable. `next(iter(extra))` takes the first (and only) key of the one-item dictionary, and that key is used as the pattern for `match`.

`tests/unit/infrastructure/test_settings.py`, lines 65 to 67:

```python
def test_settings_read_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "from-the-process")
    assert Settings.from_env().postgres.password == "from-the-process"
```

When `from_env` is called with no argument it must read the real process environment. `monkeypatch.setenv` sets a variable only for this test and removes it afterwards.

#### `tests/unit/interfaces/test_cli.py`

The two command-line programs (`run_cli` and `health_cli`) return an integer exit code: 0 for success, 1 for a lab error, 2 for bad configuration and 130 for an interrupted run (128 plus 2, the number of `SIGINT`). These tests call the `main` function directly with a list of arguments instead of starting a new process.

`tests/unit/interfaces/test_cli.py`, lines 1 to 6:

```python
import pytest

from slow_queries.application.health import ProbeFailedError
from slow_queries.interfaces import health_cli, run_cli

from ..application.fakes import FakeDatabase, RecordingStore
```

The imports include the two program modules and the fakes from the application tests, reached with `..application.fakes` (two dots mean "go up one package, then into `application`").

`tests/unit/interfaces/test_cli.py`, lines 9 to 13:

```python
def test_a_missing_password_is_a_configuration_error_with_exit_code_2(monkeypatch, capsys):
    monkeypatch.delenv("PGPASSWORD", raising=False)
    assert health_cli.main([]) == 2
    assert "PGPASSWORD" in capsys.readouterr().err
    assert run_cli.main([]) == 2
```

`monkeypatch.delenv("PGPASSWORD", raising=False)` removes the variable for the duration of the test, and `raising=False` means "do not complain if it was not set". Both programs must then return 2. `capsys` captures what was printed: `capsys.readouterr().err` is the text sent to standard error, which must name `PGPASSWORD`.

`tests/unit/interfaces/test_cli.py`, lines 16 to 22:

```python
def test_the_run_command_replays_against_the_database_it_is_given(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")
    monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda _settings, _sql_dir: FakeDatabase())
    assert run_cli.main(["--output-dir", str(tmp_path), "--repetitions", "2"]) == 0
    assert (tmp_path / "results.md").exists()
    assert (tmp_path / "q1_day_before.txt").exists()
    assert "no new indexes" in capsys.readouterr().out
```

`monkeypatch.setenv("PGPASSWORD", "x")` supplies a throwaway password. `monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda ...: FakeDatabase())` replaces the name `PostgresLabDatabase` inside the `run_cli` module with a function that returns a fake, so no connection is made. `tmp_path` is a fresh empty folder that pytest creates for this test. The program is run with `--output-dir` and `--repetitions 2`, must return 0, and must have written `results.md` and a plan file into that folder; the printed output must contain the write-cost label `no new indexes`.

`tests/unit/interfaces/test_cli.py`, lines 25 to 36:

```python
def test_a_stop_request_gives_exit_code_130(monkeypatch, tmp_path):
    monkeypatch.setenv("PGPASSWORD", "x")
    monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda _settings, _sql_dir: FakeDatabase())

    class AlreadyStopped:
        requested = True

        def install(self) -> None:
            pass

    monkeypatch.setattr(run_cli, "ShutdownSignal", AlreadyStopped)
    assert run_cli.main(["--output-dir", str(tmp_path)]) == 130
```

To test the interrupted case without sending a signal, the test defines a class `AlreadyStopped` with `requested = True` and an `install` method that does nothing, and swaps it in for `ShutdownSignal`. The replay then sees a stop request at its first check and the program must return 130. Defining the class inside the test keeps this stand-in out of the module's namespace.

`tests/unit/interfaces/test_cli.py`, lines 39 to 53:

```python
def test_health_is_exit_1_when_the_probe_fails(monkeypatch, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")

    class Failing:
        name = "postgres"

        def __init__(self, _settings) -> None:
            pass

        def check(self) -> str:
            raise ProbeFailedError("the orders table is missing; run make db")

    monkeypatch.setattr(health_cli, "PostgresOrdersProbe", Failing)
    assert health_cli.main([]) == 1
    assert "FAIL postgres: the orders table is missing" in capsys.readouterr().out
```

`Failing` stands in for the health probe class: it takes the settings in its constructor (ignored), has a `name`, and raises `ProbeFailedError` from `check`. After it replaces `PostgresOrdersProbe`, `health_cli.main([])` must return 1 and print a line beginning `FAIL postgres:` followed by the reason.

`tests/unit/interfaces/test_cli.py`, lines 56 to 70:

```python
def test_health_is_exit_0_when_the_probe_passes(monkeypatch, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")

    class Passing:
        name = "postgres"

        def __init__(self, _settings) -> None:
            pass

        def check(self) -> str:
            return "1,000,000 orders, statistics fresh"

    monkeypatch.setattr(health_cli, "PostgresOrdersProbe", Passing)
    assert health_cli.main([]) == 0
    assert "ok postgres" in capsys.readouterr().out
```

The mirror case: `Passing.check` returns a status text, the program returns 0 and prints a line containing `ok postgres`.

`tests/unit/interfaces/test_cli.py`, lines 73 to 76:

```python
@pytest.mark.parametrize("argument", ["--repetitions", "x"])
def test_a_bad_argument_is_rejected_by_the_parser(argument):
    with pytest.raises(SystemExit):
        run_cli.main([argument])
```

This is the parametrized test of this file. It runs twice: once with the argument list `["--repetitions"]` (an option that needs a value but has none) and once with `["x"]` (an argument the parser does not know). `argparse`, Python's command-line parser, prints a usage message and ends the program by raising `SystemExit`, and the test expects exactly that.

`tests/unit/interfaces/test_cli.py`, lines 79 to 82:

```python
def test_the_recording_store_is_usable_as_a_port():
    store = RecordingStore()
    store.save_plan("a", ["x"])
    assert store.plans == {"a": ("x",)}
```

The last test checks the fake itself: a `RecordingStore` must really behave as the `save_plan` part of the port, and keeps lines as a tuple. If the fake were wrong, all the replay tests above would be testing a lie.

#### `tests/integration/test_lesson_outcomes.py`

These tests need a running PostgreSQL with the seeded `orders` table (`make up`, then `make db`). There is one test per "Done when" line of the lesson. The line `pytestmark = pytest.mark.integration` below marks every test in the file with `integration`; `make test` runs only `tests/unit`, and `make test-integration` runs `tests/integration -m integration`. `--strict-markers` in `pyproject.toml` makes pytest refuse a marker that was not declared there, which catches a misspelled one.

`tests/integration/test_lesson_outcomes.py`, lines 1 to 12:

```python
"""One test per "Done when" line of the lesson, against the seeded database (make up db first)."""

import pathlib

import pytest

from slow_queries.domain.errors import UnknownStepError
from slow_queries.domain.plan import parse_text_plan
from slow_queries.infrastructure.lab_database import PostgresLabDatabase
from slow_queries.infrastructure.sql_script import run_file

pytestmark = pytest.mark.integration
```

Line 1 is the module docstring. `pathlib` is for paths; `UnknownStepError` is raised when the lab is asked for a migration that does not exist; `parse_text_plan` reads plan text; `PostgresLabDatabase` is the real database adapter; `run_file` runs a whole SQL file.

`tests/integration/test_lesson_outcomes.py`, lines 14 to 23:

```python
DAY_RANGE = "SELECT * FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15'"
DAY_FUNCTION = "SELECT * FROM orders WHERE date(created_at) = '2026-03-14'"
LATEST = "SELECT * FROM orders WHERE customer_id = {customer} ORDER BY created_at DESC LIMIT 10"
LISTING = (
    "FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' "
    "ORDER BY created_at DESC"
)
LISTING_WIDE = "SELECT * " + LISTING
LISTING_NARROW = "SELECT id, customer_id, status, created_at, total " + LISTING
SMALL_CUSTOMER = 31337
```

These constants are the exact queries of the lesson, written once. `DAY_FUNCTION` filters with `date(created_at) = ...`, which wraps the column in a function so that an ordinary index on `created_at` cannot be used; `DAY_RANGE` asks for the same day as a range of timestamps, which an index can serve. `LATEST` has a `{customer}` placeholder that `.format` fills in later. `LISTING` is only the tail of a query (the `FROM` and the rest), so that `LISTING_WIDE` (`SELECT *`) and `LISTING_NARROW` (five named columns) can share it; Python joins the two adjacent string pieces in the parentheses into one string. `SMALL_CUSTOMER` is a customer with only a few orders.

`tests/integration/test_lesson_outcomes.py`, lines 26 to 41:

```python
def test_the_seed_has_the_intended_skew_and_fresh_statistics(connection):
    total, heavy = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50) FROM orders"
    ).fetchone()
    assert total == 1_000_000
    assert 0.55 <= heavy / total <= 0.65, "customers 1-50 should hold about 60% of the rows"
    biggest, typical = connection.execute(
        "SELECT max(orders), percentile_cont(0.5) WITHIN GROUP (ORDER BY orders) "
        "FROM (SELECT count(*) AS orders FROM orders GROUP BY customer_id) AS per_customer"
    ).fetchone()
    assert biggest > 10_000
    assert typical < 20
    analyzed = connection.execute(
        "SELECT coalesce(last_analyze, last_autoanalyze) FROM pg_stat_user_tables WHERE relname = 'orders'"
    ).fetchone()[0]
    assert analyzed is not None, "statistics must be fresh before any plan is trusted"
```

The first test checks the seed data itself. `connection.execute(sql).fetchone()` runs a query and returns its first row as a tuple, which is unpacked into two names. `count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50)` counts only the rows of the 50 heavy customers. The test requires exactly 1,000,000 rows and between 55 and 65 percent of them in those customers. The second query counts the orders of each customer in a subquery, then takes the largest count and the **median** (`percentile_cont(0.5) WITHIN GROUP (ORDER BY ...)`, the middle value); the lesson depends on a few customers having more than 10,000 orders while a typical one has fewer than 20. The third query reads when the table was last analyzed (`ANALYZE` collects the statistics the planner uses; `coalesce` takes the first value that is not null, here the manual or else the automatic one) and demands that it exists. The text after the comma in each `assert` is shown if the assertion fails.

`tests/integration/test_lesson_outcomes.py`, lines 44 to 47:

```python
def test_a_function_on_the_column_forces_a_full_scan_that_discards_almost_every_row(database):
    plan = database.explain_json(DAY_FUNCTION)
    assert plan.has_node("Seq Scan")
    assert plan.rows_removed_by_filter > 990_000
```

`database` is a fixture (from `conftest.py`) that resets the table to its primary key alone. `explain_json` runs the query under `EXPLAIN (ANALYZE, BUFFERS, ...)` in JSON format and parses the result. With a function on the column the plan must contain a `Seq Scan`, and the filter must have discarded more than 990,000 of the million rows.

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

Step 1 creates `idx_orders_created_at`. The test records the plan of the function query before, applies the step, and records the plan of the range query after. After the step there must be no sequential scan, the new index must be used, and both the time and the page count must have dropped at least tenfold. The comment on the last assert says why pages are also checked: a clock can be disturbed by other programs on the machine, a page count cannot.

`tests/integration/test_lesson_outcomes.py`, lines 60 to 71:

```python
@pytest.mark.parametrize("customer", [7, SMALL_CUSTOMER])
def test_latest_orders_read_ten_index_entries_with_no_sort_for_heavy_and_small_customers(
    database, connection, customer
):
    database.reset_to(2)
    plan = database.explain_json(LATEST.format(customer=customer))
    assert not plan.has_node("Sort"), f"customer {customer} still sorts"
    assert plan.uses_index("idx_orders_customer_created")
    assert plan.pages <= 20, "ten index entries and their rows, whatever the customer's total"
    returned = connection.execute(LATEST.format(customer=customer)).fetchall()
    expected = connection.execute("SELECT least(10, count(*)) FROM orders WHERE customer_id = %s", (customer,))
    assert len(returned) == expected.fetchone()[0]
```

This test runs twice because of `parametrize`: once for customer 7, a heavy customer, and once for the small one. `database.reset_to(2)` puts the table in the state after step 2 (the index on customer and creation time). The plan must have no `Sort` node (the index already stores orders in time order, so the newest ten can be read from its end), must use that index, and must touch at most 20 pages. The f-string `f"customer {customer} still sorts"` puts the value into the failure message. The last three lines also run the query for real and compare the number of rows returned with `least(10, count(*))`, the expected count, so a plan that is fast but wrong would be caught. `%s` is psycopg's placeholder for a value passed separately in a tuple, which keeps values out of the SQL text.

`tests/integration/test_lesson_outcomes.py`, lines 74 to 81:

```python
def test_a_covering_index_gives_an_index_only_scan_with_fewer_pages(database):
    database.reset_to(2)
    wide = database.explain_json(LISTING_WIDE)
    database.apply_step(3)
    narrow = database.explain_json(LISTING_NARROW)
    assert narrow.has_node("Index Only Scan")
    assert narrow.heap_fetches == 0, "the visibility map is current, so the heap is never visited"
    assert narrow.pages * 1.5 < wide.pages
```

Step 3 creates a covering index, which stores extra columns so that the query never needs the table. The wide `SELECT *` query cannot be answered from it, so it is measured before the step; the five-column query is measured after. The narrow plan must contain an `Index Only Scan`, zero heap fetches (the **visibility map**, a per-page flag that says all rows on a page are visible to every transaction, is current, so the table is never visited) and at least a third fewer pages (`narrow.pages * 1.5 < wide.pages`).

`tests/integration/test_lesson_outcomes.py`, lines 84 to 87:

```python
def test_a_big_out_of_line_column_costs_pages_only_when_it_is_selected(database):
    wide = parse_text_plan(database.capture_plan("q3_toast_wide"))
    narrow = parse_text_plan(database.capture_plan("q3_toast_narrow"))
    assert wide.pages > 20 * narrow.pages, "detoasting reads the TOAST table"
```

Large values such as the order's note are stored outside the main table in a side table called the TOAST table (The Oversized-Attribute Storage Technique). Reading the column makes PostgreSQL visit that side table, which costs pages. The two captures read the same data with and without the note column, and the wide one must touch more than 20 times as many pages.

`tests/integration/test_lesson_outcomes.py`, lines 90 to 100:

```python
def test_each_index_adds_write_work_and_the_batches_are_rolled_back(database):
    rows_before = database.row_count()
    bare = database.measure_write_cost(repetitions=2)
    database.reset_to(2)
    two_indexes = database.measure_write_cost(repetitions=2)
    database.reset_to(4)
    after_drop = database.measure_write_cost(repetitions=2)
    assert two_indexes.wal_records >= bare.wal_records + 2 * 9_000, "about 10,000 records per index"
    assert two_indexes.pages > bare.pages
    assert bare.wal_records < after_drop.wal_records < two_indexes.wal_records + 1_000
    assert database.row_count() == rows_before
```

Each extra index must be kept up to date on every insert. The test measures the write batch with no new index, after step 2 (two indexes), and after step 4 (only the covering index). `repetitions=2` runs the batch twice and takes the median. With two indexes the log must hold at least `bare + 2 * 9_000` more WAL records, about 10,000 per index with some room. Pages must grow too. The third assert is a chained comparison: after dropping one index the cost must lie between the bare table and the two-index cost. The last line checks that the number of rows in the table is the same as at the start, which proves each batch was rolled back.

`tests/integration/test_lesson_outcomes.py`, lines 103 to 113:

```python
def test_the_committed_plans_say_what_the_readme_says():
    explain = pathlib.Path(__file__).resolve().parents[2] / "sql" / "explain"

    def plan(name):
        return parse_text_plan((explain / f"{name}.txt").read_text().splitlines())

    assert plan("q1_day_before").has_node("Seq Scan")
    assert plan("q1_day_after").uses_index("idx_orders_created_at")
    assert plan("q2_latest_whale_before").has_node("Sort")
    assert not plan("q2_latest_whale_after").has_node("Sort")
    assert plan("q3_listing_after").uses_index("idx_orders_listing")
```

This test reads files rather than the database. The plan texts committed in `sql/explain` are what the lesson's README points at, so they must show what the README says. `plan(name)` is a small function defined inside the test: it reads `<name>.txt` and parses it. The five assertions check the headline facts: a sequential scan before step 1, the new index after it, a sort in the heavy customer's plan before step 2 and none after, and the covering index in the final listing plan.

`tests/integration/test_lesson_outcomes.py`, lines 116 to 127:

```python
def test_migrations_can_run_twice_and_be_reverted_twice_without_harm(database):
    for number in (1, 2, 3, 4):
        database.apply_step(number)
        database.apply_step(number)
    assert set(database.index_sizes()) == {"orders_pkey", "idx_orders_created_at", "idx_orders_listing"}
    database.revert_step(4)
    database.revert_step(4)
    assert "idx_orders_customer_created" in database.index_sizes(), "down 004 brings the narrow index back"
    for number in (3, 2, 1):
        database.revert_step(number)
        database.revert_step(number)
    assert set(database.index_sizes()) == {"orders_pkey"}
```

Migrations must be safe to run twice and to undo twice. The loop applies every step two times. The set of index names must then be exactly the primary key, the created-at index and the covering index (step 4 dropped the customer index). Reverting step 4 twice must bring `idx_orders_customer_created` back (the message after the comma explains why). The final loop reverts steps 3, 2 and 1 in reverse order, twice each, and only the primary key may remain.

`tests/integration/test_lesson_outcomes.py`, lines 130 to 133:

```python
def test_the_seed_script_leaves_tables_that_have_rows_alone():
    seed = (pathlib.Path(__file__).resolve().parents[2] / "sql" / "002_seed.sql").read_text()
    assert "\\if :orders_empty" in seed
    assert "\\if :demo_empty" in seed
```

The seed script must not reload data into a table that already has rows. It does this with psql's `\if` conditional on a variable it sets by looking at the table. The test reads the script's text and checks that the two guards are there, one for `orders` and one for the demo table.

`tests/integration/test_lesson_outcomes.py`, lines 136 to 140:

```python
def test_a_step_the_lesson_does_not_have_is_refused(database):
    with pytest.raises(UnknownStepError):
        database.apply_step(5)
    with pytest.raises(UnknownStepError):
        database.revert_step(0)
```

Asking for step 5 or reverting step 0 must raise `UnknownStepError`, not run something unexpected.

`tests/integration/test_lesson_outcomes.py`, lines 143 to 146:

```python
def test_the_schema_script_can_run_twice(connection, settings):
    run_file(connection, settings.sql_dir / "001_schema.sql")
    run_file(connection, settings.sql_dir / "001_schema.sql")
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1_000_000
```

The schema script uses `CREATE ... IF NOT EXISTS`, so running it twice changes nothing. The test runs the real file twice with `run_file` and checks that the million rows are still there.

`tests/integration/test_lesson_outcomes.py`, lines 149 to 150:

```python
def test_the_adapter_is_usable_as_the_port(database: PostgresLabDatabase):
    assert len(database.migrations()) == len(database.down_migrations()) == 4
```

The type hint `database: PostgresLabDatabase` plus the call to `migrations()` and `down_migrations()` checks that the adapter provides what the port promises, and that the lesson has four up scripts and four down scripts.

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

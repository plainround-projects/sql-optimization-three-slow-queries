# Python

## What it is

**Python** is a programming language: you write instructions in a text file (a `.py` file), and a program called the **interpreter** reads the file and carries the instructions out one after another. It is known for being readable, and it comes with a large **standard library** of ready-made tools (files, text, dates, networking). Python is **dynamically typed** (a name can hold any kind of value, checked when the line runs), but it supports optional **type hints** that other tools check beforehand (see the typing note).

## Why this repository uses it

The lab's programs are Python: they connect to PostgreSQL, run the migration files, ask the database for query plans, read the plans as text and write the results. Python is also the language of the tests. The code is arranged in four layers; this note walks through the layers `domain`, `application` and the shared start-up code of `interfaces`. The other modules are explained where their main technology is: `infrastructure/postgres.py` and `lab_database.py` in the psycopg note, `settings.py` in the environment-variables note, `logging.py` in the logging note, `shutdown.py`, `run_cli.py` and `health_cli.py` in the command-line note, `artifacts.py`, `retry.py` and `sql_script.py` in the standard-library note.

## Where it appears

| Folder | What is there |
|---|---|
| `src/slow_queries/domain/` | Pure rules: errors, host load, lesson steps, plan parsing, write cost, comparison. No input or output. |
| `src/slow_queries/application/` | The replay and health use cases, the report, and the ports (interfaces) they need. |
| `src/slow_queries/infrastructure/` | The code that touches the outside world. |
| `src/slow_queries/interfaces/` | The programs started from the command line. |
| `tests/` | Unit, integration and end-to-end tests (pytest note). |

## How it works underneath

**Running.** `python file.py` starts the interpreter as a process, which compiles the file into **bytecode** (a compact internal form), then runs it. `python -m package.module` runs a module found through the import system; the code under `if __name__ == "__main__":` runs only when the file is started this way, not when it is imported.

**Names and values.** `x = 5` makes the name `x` refer to the value 5. Values have types: `int` (whole numbers), `float` (numbers with a fraction), `str` (text), `bool` (`True` or `False`), `None` (no value), `list` (`[1, 2]`, changeable), `tuple` (`(1, 2)`, fixed), `dict` (`{"a": 1}`, name-to-value map), `set` (`{1, 2}`, unique items).

**Blocks are indented.** After a line ending in `:` (`if`, `for`, `def`, `class`, `try`, `with`), the following lines indented four spaces are its body.

**Statements you will meet.**

- `import module` and `from module import name` load code from another file. A leading dot (`from .plan import X`, `from ..domain import Y`) is a **relative import**: `.` means this package, `..` the parent package.
- `def name(parameters) -> result:` defines a **function**. `*` in the parameter list means "everything after this must be passed by name" (keyword-only). A default value (`attempts: int = 5`) makes an argument optional. `return value` ends the function with a result.
- `class Name:` defines a **class**: a recipe for objects bundling data and functions (**methods**). `self` is the object a method works on. `__init__` runs when an object is created. A class in parentheses (`class LabError(Exception)`) **inherits** from another class. A leading underscore (`_name`) marks something as private by convention.
- `@decorator` above a function or class passes it through another function that wraps or changes it. `@property` turns a method into something read like an attribute (`obj.speedup`); `@classmethod` makes a method that works on the class, not an object.
- `if` / `elif` / `else`, `for item in things:`, `while`, `break`, `continue`.
- `try:` / `except ErrorType as error:` / `finally:` handle errors. `raise Error("text")` creates one. `raise X from y` records that `y` was the cause. `finally` always runs.
- `with something as name:` runs a block with a **context manager** that sets up and always cleans up (a file closed, a connection closed).
- `assert condition, "message"` raises `AssertionError` if the condition is false.
- `yield` makes a function a **generator**: it produces values one at a time when asked. `yield from other` hands over the values of another generator.
- `lambda x: expression` is a one-line anonymous function.

**Expressions.** F-strings, `f"{value:.3f}"`, put values into text; after the colon comes a **format**: `.3f` is three digits after the point, `,` adds thousands separators, `8.1f` means width 8 with one decimal. A **comprehension** builds a collection in one line: `[x * 2 for x in items if x > 0]` (list), `{k: v for ...}` (dict), `(x for x in ...)` (generator). `a if condition else b` picks one. `*` before a collection inside brackets spreads its items: `[*first, *second]`. Slicing `items[1:5]` takes a range; `text[:60]` the first 60 characters.

**Truthiness.** `if items:` is true when the list is not empty; empty text, `0` and `None` are false.

**Errors.** An uncaught error ends the program with a **traceback**, a list of the lines that led to it, and exit code 1.

**Modules and packages.** One `.py` file is a module; a folder with `__init__.py` is a package. `__name__` is the module's name, or `"__main__"` when it was started directly. `__file__` is its path.

## Walkthrough of this repository's use

### `domain/errors.py`

`src/slow_queries/domain/errors.py`, lines 1 to 17:

```python
"""Named errors of the lesson. Each says what went wrong in terms a reader of the plans would use."""


class LabError(Exception):
    """Base class of every error this package raises on purpose."""


class PlanParseError(LabError):
    """A query plan did not have the lines or fields the lesson reads."""


class UnknownStepError(LabError):
    """A migration step number outside the lesson's steps."""


class LessonInterruptedError(LabError):
    """The replay was asked to stop (SIGINT or SIGTERM) between two steps."""
```

Line 1 is a **docstring**: a text in triple quotes as the first statement of a module, class or function; tools show it as documentation. `class LabError(Exception):` defines a new kind of error that **inherits** from Python's built-in `Exception`. The body is only a docstring, which is enough to make a valid class. The other three classes inherit from `LabError`, so code can catch every error this package raises on purpose with `except LabError`, or one specific kind. Names end in `Error` by a convention that ruff checks (rule `N818`).

### `domain/host.py`

`src/slow_queries/domain/host.py`, lines 1 to 27:

```python
"""How busy the machine was while something was measured, so a reader can discount the milliseconds."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HostLoad:
    """The 1-minute load average and the CPU count at the start of a measurement."""

    load_average: float
    cpus: int

    @property
    def loaded(self) -> bool:
        """True when more than half a runnable task per CPU was waiting: timings are inflated."""
        return self.load_average > self.cpus / 2

    def note(self) -> str:
        """One sentence for the results file."""
        if self.loaded:
            return (
                f"Measured on a loaded machine (load average {self.load_average:.1f} on {self.cpus} CPUs); rerun "
                "`make run` on a quiet machine for clean figures. The ratios survive load better than the milliseconds."
            )
        return f"Measured at load average {self.load_average:.1f} on {self.cpus} CPUs."
```

- Line 3 `from __future__ import annotations` makes type hints be stored as text and evaluated lazily (typing note).
- Line 5 imports `dataclass`; lines 8 to 13 define a class with two fields; the dataclass note explains what the decorator generates.
- `@property def loaded(self) -> bool:` is read as `host_load.loaded`, without parentheses. It compares the load average with half the number of CPUs; `>` gives a `bool`.
- `note` returns text. `if self.loaded:` chooses the branch. Inside the `return (...)`, two string literals side by side are joined into one by Python. The first is an **f-string** (prefix `f`): `{self.load_average:.1f}` inserts the number with one decimal, `{self.cpus}` inserts the CPU count. The backticks inside the text are just characters (they make Markdown show code).
- The second `return` is the quiet-machine case.

### `domain/comparison.py`

`src/slow_queries/domain/comparison.py`, lines 1 to 25:

```python
"""Before-and-after of one query: the ratio is what the lesson teaches, the milliseconds are only the evidence."""

from __future__ import annotations

from dataclasses import dataclass

from .plan import PlanSummary


@dataclass(frozen=True, slots=True)
class Improvement:
    """A plan before a change and the same query's plan after it."""

    before: PlanSummary
    after: PlanSummary

    @property
    def speedup(self) -> float:
        """How many times faster the query got; a zero-millisecond result counts as 0.001 ms."""
        return self.before.execution_ms / max(self.after.execution_ms, 0.001)

    @property
    def pages_ratio(self) -> float:
        """How many times fewer pages the query touches (at least one page after)."""
        return self.before.pages / max(self.after.pages, 1)
```

- `from .plan import PlanSummary` is a relative import: the module `plan` in the same package.
- `Improvement` has two fields, `before` and `after`, both of type `PlanSummary`.
- `speedup` divides the old time by the new time. `max(self.after.execution_ms, 0.001)` returns the larger of the two numbers, so the divisor is never smaller than 0.001: a query that took 0 milliseconds cannot cause a division by zero.
- `pages_ratio` does the same with page counts, with a floor of 1.

### `domain/lesson.py`

`src/slow_queries/domain/lesson.py`, lines 1 to 47:

```python
"""The lesson as data: which index each step adds and which plans are read before and after it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndexStep:
    """One change: apply migration `number`, then read the plans named in `captures`."""

    number: int
    label: str
    captures: tuple[str, ...]


INDEX_NAMES = ("idx_orders_created_at", "idx_orders_customer_created", "idx_orders_listing")

#: Plans read with only the primary key in place.
BEFORE_ANY_INDEX = (
    "q1_day_before",
    "q2_latest_whale_before",
    "q2_latest_small_before",
    "q3_toast_wide",
    "q3_toast_narrow",
)

STEPS = (
    IndexStep(1, "+ idx_orders_created_at", ("q1_day_after",)),
    IndexStep(
        2,
        "+ idx_orders_customer_created",
        ("q2_latest_whale_after", "q2_latest_small_after", "q3_listing_before", "q3_listing_narrow"),
    ),
    IndexStep(3, "+ idx_orders_listing", ("q3_listing_after",)),
    IndexStep(4, "idx_orders_listing only (idx_orders_customer_created dropped)", ()),
)

#: (label, plan before, plan after) rows of the comparison table.
COMPARISONS = (
    ("q1 day query", "q1_day_before", "q1_day_after"),
    ("q2 latest 10, heavy customer", "q2_latest_whale_before", "q2_latest_whale_after"),
    ("q2 latest 10, small customer", "q2_latest_small_before", "q2_latest_small_after"),
    ("q3 listing: SELECT * vs covering index", "q3_listing_before", "q3_listing_after"),
    ("q3 listing: five columns, no covering index", "q3_listing_before", "q3_listing_narrow"),
    ("q3 TOAST demo: SELECT * vs without the note", "q3_toast_wide", "q3_toast_narrow"),
)
```

- `IndexStep` (lines 8 to 14) is a small record: a migration `number`, a text `label`, and `captures: tuple[str, ...]`, a tuple of any length whose items are text (`...` means "any number").
- Line 17: `INDEX_NAMES` is a tuple of the three index names. A name written in capital letters is a **constant** by convention.
- Line 19: `#:` is a comment style that documentation tools pick up. `BEFORE_ANY_INDEX` lists the plans read before any change.
- Lines 28 to 37: `STEPS` is a tuple of four `IndexStep` objects, created by calling the class with positional arguments (`IndexStep(1, "+ idx_orders_created_at", ("q1_day_after",))`). A one-item tuple needs a trailing comma, `("q1_day_after",)`; the last step has an empty tuple `()`.
- Lines 40 to 47: `COMPARISONS` lists `(label, name of the plan before, name of the plan after)` triples. The replay uses them to build the results table.

### `domain/plan.py` (the functions; the regular expressions are in their own note)

`src/slow_queries/domain/plan.py`, lines 1 to 14:

```python
"""What the lesson reads from a query plan: time, pages, node types, indexes and rows discarded.

Both plan formats are parsed here and nowhere else: the text of `EXPLAIN (ANALYZE, BUFFERS)` (what the
`.txt` files hold) and its JSON form (what the tests assert on). No I/O.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import PlanParseError
```

A multi-line docstring explains the module. Line 9 imports `re`, Python's regular-expression module. Line 10 imports abstract type names from `collections.abc`: `Iterable` (anything you can loop over), `Iterator` (something that produces values one by one), `Mapping` (dict-like, read-only), `Sequence` (list-like). Line 11 imports `dataclass`; line 12 `Any` ("any type"); line 14 the error `PlanParseError` from the sibling module.

`src/slow_queries/domain/plan.py`, lines 25 to 43:

```python
@dataclass(frozen=True, slots=True)
class PlanSummary:
    """One executed plan, reduced to the numbers the lesson compares."""

    execution_ms: float
    pages: int
    node_types: tuple[str, ...]
    index_names: tuple[str, ...]
    rows_removed_by_filter: int
    heap_fetches: int | None

    def has_node(self, node_type: str) -> bool:
        """True when any node of the plan has exactly this type, for example `Seq Scan` or `Sort`."""
        return node_type in self.node_types

    def uses_index(self, name: str) -> bool:
        """True when the plan reads the named index (index scan, index-only scan or bitmap index scan)."""
        return name in self.index_names

```

`PlanSummary` holds the numbers the lesson compares. `heap_fetches: int | None` means "a whole number or nothing" (`None`); it is `None` for plans without an index-only scan. The two methods answer yes/no questions: `node_type in self.node_types` tests whether a text is in the tuple. `has_node("Seq Scan")` is true if any step of the plan is a sequential scan.

`src/slow_queries/domain/plan.py`, lines 45 to 59:

```python
def parse_text_plan(lines: Sequence[str]) -> PlanSummary:
    """Summarize the text of an `EXPLAIN (ANALYZE, BUFFERS)` plan."""
    text = "\n".join(lines)
    execution = _EXECUTION.search(text)
    if execution is None:
        raise PlanParseError("no 'Execution Time' line: was the plan produced with ANALYZE?")
    heap_fetches = _HEAP_FETCHES.search(text)
    return PlanSummary(
        execution_ms=float(execution.group(1)),
        pages=pages_touched(lines),
        node_types=tuple(node.strip() for node in _NODE.findall(text)),
        index_names=tuple(dict.fromkeys(_INDEX.findall(text))),
        rows_removed_by_filter=sum(int(count) for count in _REMOVED.findall(text)),
        heap_fetches=int(heap_fetches.group(1)) if heap_fetches else None,
    )
```

`parse_text_plan(lines)` receives the plan as a sequence of text lines. `"\n".join(lines)` glues them into one text with line breaks (`"\n"` is the new-line character). `_EXECUTION.search(text)` looks for the first match of a regular expression and returns a match object, or `None`. `if execution is None: raise PlanParseError(...)` stops with a named error when the "Execution Time" line is missing. The `PlanSummary(...)` call fills the fields by name: `float(execution.group(1))` converts the matched digits to a number; `tuple(node.strip() for node in _NODE.findall(text))` is a **generator expression** inside `tuple(...)`: it takes every match of the node-type pattern, removes surrounding spaces with `.strip()` and collects them. `dict.fromkeys(...)` makes a dictionary whose keys are the items; since dictionary keys are unique and keep their order, wrapping a list in `dict.fromkeys` removes duplicates while keeping order. `sum(int(count) for count in _REMOVED.findall(text))` adds up all the "Rows Removed by Filter" numbers. `int(heap_fetches.group(1)) if heap_fetches else None` is a conditional expression.

`src/slow_queries/domain/plan.py`, lines 62 to 76:

```python
def pages_touched(lines: Iterable[str]) -> int:
    """Pages a plan touched: the top node's `Buffers: shared hit=.. read=..`, plus the pages read to send the rows.

    The second figure is the `Buffers` line after `Serialization:`, where out-of-line (TOAST) values are fetched.
    """
    total, after_serialization = 0, False
    for line in lines:
        if line.startswith("Serialization:"):
            after_serialization = True
            continue
        match = _BUFFERS.search(line)
        if match and (after_serialization or total == 0):
            total += sum(int(count) for count in _PAGE_COUNTS.findall(match.group(1)))
            after_serialization = False
    return total
```

`pages_touched` reads the "Buffers" lines. `total, after_serialization = 0, False` assigns two names at once (a tuple). The loop `for line in lines:` visits each line. `line.startswith("Serialization:")` is a text test; `continue` jumps to the next line. `match and (...)` uses **short-circuit** logic: if `match` is `None` the right side is not evaluated. `total += ...` adds to `total`. `match.group(1)` is the text captured by the first parenthesis of the pattern, and `_PAGE_COUNTS.findall(...)` returns every number after `hit=` or `read=`. So the function adds hits and reads of the top node, plus those of the line after `Serialization:`.

`src/slow_queries/domain/plan.py`, lines 79 to 100:

```python
def _json_nodes(node: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    yield node
    for child in node.get("Plans", []):
        yield from _json_nodes(child)


def parse_json_plan(document: Mapping[str, Any]) -> PlanSummary:
    """Summarize one element of the JSON that `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` returns."""
    try:
        root = document["Plan"]
        nodes = list(_json_nodes(root))
        fetches = [node["Heap Fetches"] for node in nodes if "Heap Fetches" in node]
        return PlanSummary(
            execution_ms=float(document["Execution Time"]),
            pages=int(root["Shared Hit Blocks"]) + int(root["Shared Read Blocks"]),
            node_types=tuple(node["Node Type"] for node in nodes),
            index_names=tuple(dict.fromkeys(node["Index Name"] for node in nodes if "Index Name" in node)),
            rows_removed_by_filter=sum(int(node.get("Rows Removed by Filter", 0)) for node in nodes),
            heap_fetches=int(fetches[0]) if fetches else None,
        )
    except (KeyError, TypeError) as error:
        raise PlanParseError(f"unexpected JSON plan shape: missing {error}") from error
```

`_json_nodes` is a **generator** function: `yield node` hands out the current node, then `yield from _json_nodes(child)` hands out all the nodes of each child, so the whole plan tree is walked one node at a time. This is **recursion**: the function calls itself. `node.get("Plans", [])` returns the value of the key `"Plans"` or an empty list if the key is missing. `parse_json_plan` reads the same facts from the JSON form of a plan. A **list comprehension** `[node["Heap Fetches"] for node in nodes if "Heap Fetches" in node]` picks the values from nodes that have the key. The whole body sits in `try:`; `except (KeyError, TypeError) as error:` catches the two kinds of errors a differently shaped document can cause (a missing key; a value of the wrong type) and re-raises them as a `PlanParseError` with `from error`, which keeps the original as the cause.

### `domain/write_cost.py`

`src/slow_queries/domain/write_cost.py`, lines 1 to 45:

```python
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
```

`WriteCost` has four numbers. `parse_write_cost` finds two things in the text of an `EXPLAIN (ANALYZE, BUFFERS, WAL)` plan: the WAL line and the execution time. `wal, execution = _WAL.search(text), _EXECUTION.search(text)` makes two assignments in one line. The `if wal is None or execution is None` test raises a descriptive error. `median_cost` imports `statistics` (line 6) and computes the **median** (middle value) of each figure over several runs. `if not samples:` is true for an empty list, so it raises `ValueError`. `statistics.median(sample.milliseconds for sample in samples)` passes a generator; `int(...)` converts the result of the other medians back to whole numbers.

### `application/health.py`

`src/slow_queries/application/health.py`, lines 1 to 43:

```python
"""Use case: ask every dependency whether it is usable."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .ports import HealthProbe


class ProbeFailedError(Exception):
    """A dependency is not usable; the message says why."""


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """The outcome of one health probe."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class HealthReport:
    """The outcomes of every probe; healthy only when all of them are."""

    results: tuple[ProbeResult, ...]

    @property
    def healthy(self) -> bool:
        return all(result.ok for result in self.results)


def check_health(probes: Iterable[HealthProbe]) -> HealthReport:
    """Run every probe and collect the outcomes; a failed probe is reported, not raised."""
    results = []
    for probe in probes:
        try:
            results.append(ProbeResult(probe.name, True, probe.check()))
        except ProbeFailedError as error:
            results.append(ProbeResult(probe.name, False, str(error)))
    return HealthReport(tuple(results))
```

- `ProbeFailedError(Exception)` is the error a probe raises when its dependency is unhealthy.
- `ProbeResult` and `HealthReport` are dataclasses. `results: tuple[ProbeResult, ...]` is a tuple of results.
- `healthy` uses `all(...)`, which is true only if every element of the generator is true.
- `check_health(probes)` loops over each probe object (anything with `name` and `check()`), calls `probe.check()` inside `try`, and records either a good or a failed result. A failed probe is not re-raised: the report says which one failed.
- `tuple(results)` turns the list into a tuple for the frozen dataclass.

### `application/replay.py`

`src/slow_queries/application/replay.py`, lines 1 to 50:

```python
"""Use case: replay the lesson. Plans before, one index at a time, plans after, the write cost of each index."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..domain import lesson
from ..domain.errors import LessonInterruptedError
from ..domain.host import HostLoad
from ..domain.plan import PlanSummary, parse_text_plan
from ..domain.write_cost import WriteCost
from .ports import ArtifactStore, LabDatabase
from .report import render_results


@dataclass(frozen=True, slots=True)
class LessonResult:
    """Everything the replay measured."""

    plans: dict[str, PlanSummary]
    write_costs: tuple[tuple[str, WriteCost], ...]
    index_sizes: dict[str, int]
    host_load: HostLoad | None = None


class ReplayLesson:
    """Drives the database through the lesson's steps and keeps the evidence.

    `should_stop` is polled between steps; when it returns true the replay raises `LessonInterruptedError`, so a
    SIGTERM never leaves a half-applied step behind.
    """

    def __init__(
        self,
        database: LabDatabase,
        store: ArtifactStore,
        *,
        repetitions: int = 5,
        host_load: HostLoad | None = None,
        progress: Callable[[str], None] = lambda _message: None,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self._database = database
        self._store = store
        self._repetitions = repetitions
        self._host_load = host_load
        self._progress = progress
        self._should_stop = should_stop

```

- The `ReplayLesson` class takes its collaborators in `__init__` (lines 34 to 49): `database` and `store` are required; everything after the bare `*` is keyword-only. Defaults: `repetitions=5`; `progress` defaults to `lambda _message: None`, a function that does nothing; `should_stop` defaults to `lambda: False`. The arguments are stored with a leading underscore (`self._database`), the convention for private attributes.
- `Callable[[str], None]` is the type of a function taking text and returning nothing (typing note).

`src/slow_queries/application/replay.py`, lines 51 to 71:

```python
    def run(self) -> LessonResult:
        """Replay every step, write the plans and the notes, and return what was measured."""
        rows_before = self._database.row_count()
        self._database.reset_to(0)
        plans: dict[str, PlanSummary] = {}
        for name in lesson.BEFORE_ANY_INDEX:
            self._capture(name, plans)
        write_costs = [("no new indexes", self._measure())]
        for step in lesson.STEPS:
            self._checkpoint()
            self._progress(f"step {step.number}: {step.label}")
            self._database.apply_step(step.number)
            for name in step.captures:
                self._capture(name, plans)
            write_costs.append((step.label, self._measure()))
            self._database.vacuum()
        if self._database.row_count() != rows_before:
            raise AssertionError("the write-cost batches must be rolled back; the row count changed")
        result = LessonResult(plans, tuple(write_costs), dict(self._database.index_sizes()), self._host_load)
        self._store.save_report(render_results(result))
        return result
```

`run` is the whole lesson. It remembers the row count, resets the table to "primary key only" (`reset_to(0)`), loops over `lesson.BEFORE_ANY_INDEX` and captures each plan. `write_costs = [("no new indexes", self._measure())]` starts a list with one tuple. `for step in lesson.STEPS:` visits each of the four steps: stop if asked, report progress with an f-string, apply the migration, capture the step's plans (`for name in step.captures`), add the write cost, vacuum. `if self._database.row_count() != rows_before: raise AssertionError(...)` is a safety check that the rolled-back inserts really left no rows. `LessonResult(plans, tuple(write_costs), dict(self._database.index_sizes()), self._host_load)` builds the result; `dict(...)` copies a mapping into a plain dict. The report text is produced by `render_results` and saved.

`src/slow_queries/application/replay.py`, lines 73 to 86:

```python
    def _capture(self, name: str, plans: dict[str, PlanSummary]) -> None:
        self._checkpoint()
        lines = self._database.capture_plan(name)
        self._store.save_plan(name, lines)
        plans[name] = parse_text_plan(lines)
        self._progress(f"plan {name}: {plans[name].execution_ms:.3f} ms, {plans[name].pages} pages")

    def _measure(self) -> WriteCost:
        self._checkpoint()
        return self._database.measure_write_cost(self._repetitions)

    def _checkpoint(self) -> None:
        if self._should_stop():
            raise LessonInterruptedError("stopped between steps")
```

`_capture` (the leading underscore marks a private method) calls the port to run the plan, saves it, parses it and stores the summary in the `plans` dict. `_checkpoint` raises `LessonInterruptedError` if `should_stop()` returns true, so a Ctrl-C ends the replay between two steps.

### `application/report.py`

`src/slow_queries/application/report.py`, lines 1 to 47:

```python
"""The results notes: a pure function from what was measured to Markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain import lesson
from ..domain.comparison import Improvement

if TYPE_CHECKING:
    from .replay import LessonResult


def render_results(result: LessonResult) -> str:
    """Markdown with the before-and-after table, the write cost per index set and the index sizes."""
    lines = [
        "# Results of the last `make run`",
        "",
        "Generated by `slow-queries-run`; the plans are the `.txt` files next to each `.sql` here.",
        "",
        *([result.host_load.note(), ""] if result.host_load else []),
        "| Query | Before ms | After ms | Faster | Before pages | After pages |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, before_name, after_name in lesson.COMPARISONS:
        improvement = Improvement(result.plans[before_name], result.plans[after_name])
        lines.append(
            f"| {label} | {improvement.before.execution_ms:.3f} | {improvement.after.execution_ms:.3f} "
            f"| {improvement.speedup:.0f}x | {improvement.before.pages} | {improvement.after.pages} |"
        )
    lines += [
        "",
        "## Write cost of one batch of 10,000 inserts",
        "",
        "Median of the repetitions after a warm-up, each rolled back. Pages touched and WAL records are the stable",
        "numbers (each index adds about 10,000 of each); milliseconds and WAL bytes vary with the machine.",
        "",
        "| Index set | Median ms | Pages touched | WAL records | WAL MB |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {label} | {cost.milliseconds:.1f} | {cost.pages} | {cost.wal_records} | {cost.wal_bytes / 1e6:.1f} |"
        for label, cost in result.write_costs
    ]
    lines += ["", "## Index sizes at the end", "", "| Index | Size MB |", "|---|---:|"]
    lines += [f"| {name} | {size / 1e6:.1f} |" for name, size in sorted(result.index_sizes.items())]
    return "\n".join(lines) + "\n"
```

- Lines 5 to 11: `if TYPE_CHECKING:` is false when the program runs and true only for the type checker; it lets the module mention `LessonResult` in a type hint without importing `replay`, which itself imports `report`. Importing at run time would make a circular import.
- `render_results` builds a list of text lines. `*([result.host_load.note(), ""] if result.host_load else [])` inside the list literal spreads either a two-item list (the note and an empty line) or nothing. `for label, before_name, after_name in lesson.COMPARISONS:` **unpacks** each triple into three names. f-strings with formats: `{...:.3f}` three decimals, `{improvement.speedup:.0f}x` no decimals, `{cost.wal_bytes / 1e6:.1f}` converts bytes to millions (`1e6` is one million) with one decimal. `lines += [...]` extends the list with a list comprehension. `sorted(result.index_sizes.items())` turns the dictionary into a list of `(name, size)` pairs ordered by name. The function ends with `"\n".join(lines) + "\n"`, the Markdown text ending with a line break.

### `interfaces/common.py`

`src/slow_queries/interfaces/common.py`, lines 1 to 26:

```python
"""Startup shared by the programs: settings or a clear exit code 2."""

from __future__ import annotations

import os
import sys

from ..domain.host import HostLoad
from ..infrastructure.logging import configure_logging
from ..infrastructure.settings import ConfigurationError, Settings


def load_settings() -> Settings | None:
    """Read and validate the environment, configure logging, or print the problem and return None."""
    try:
        settings = Settings.from_env()
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return None
    configure_logging(settings.log_level)
    return settings


def measure_host_load() -> HostLoad:
    """The 1-minute load average and CPU count right now, so results can say how busy the machine was."""
    return HostLoad(os.getloadavg()[0], os.cpu_count() or 1)
```

`Settings | None` in the return type means "a Settings object, or None". `try: ... except ConfigurationError as error:` prints the problem and returns `None`; `print(..., file=sys.stderr)` writes to the **standard error** channel. `measure_host_load` calls `os.getloadavg()[0]` — the first of three load numbers (1, 5 and 15 minutes) — and `os.cpu_count() or 1`, which uses 1 if the count is unknown (`or` returns its right side when the left is `None` or 0).

### The headers and imports not quoted elsewhere

#### Reading the top of a module

Most modules start with the same three parts, explained once here so that the sections below can be short. First a **docstring**: a text in triple quotes as the very first statement of a file; Python keeps it as the description of the module, and tools show it as help. Then `from __future__ import annotations`, a line that tells Python to treat type hints (the `: int` and `-> str` annotations) as plain text that is not evaluated while the file loads; this lets a hint refer to a class that is defined further down. Then the imports: `import x` makes the module `x` available; `from x import y` brings one name out of it; a dot in front, as in `from .postgres import session`, means "the module `postgres` in this same package" and two dots, `from ..domain.errors import ...`, mean "go up one package, then into `domain`". The logger line `logger = logging.getLogger(__name__)` creates a logger named after the module (`__name__` is the module's dotted name), so every log line says which module wrote it.

##### The `__init__.py` files

A folder is a Python **package** when it contains a file called `__init__.py`. The file may be empty or hold only a docstring, as these do. Each of the four layers has one, and its docstring states the layer's rule.

`src/slow_queries/domain/__init__.py`, lines 1 to 1:

```python
"""The lesson itself: plans, costs and comparisons. Depends on nothing."""
```

`src/slow_queries/application/__init__.py`, lines 1 to 1:

```python
"""Use cases and the ports they need; no knowledge of PostgreSQL."""
```

`src/slow_queries/infrastructure/__init__.py`, lines 1 to 1:

```python
"""Adapters: PostgreSQL, files, settings, logging, retries and shutdown of the lab."""
```

`src/slow_queries/interfaces/__init__.py`, lines 1 to 1:

```python
"""Entry points: the command-line programs of the lab."""
```


##### `lab_database.py` and `health_probes.py`, the top of the file

`src/slow_queries/infrastructure/lab_database.py`, lines 1 to 1:

```python
"""Adapter: the orders table in PostgreSQL, changed by the repository's migration files. Implements `LabDatabase`."""
```

The docstring names the role: an **adapter** (the code that connects the lab's own interface, `LabDatabase`, to a real tool, here PostgreSQL) for the orders table, which changes the table by running the repository's migration files.

`src/slow_queries/infrastructure/lab_database.py`, lines 9 to 16:

```python
from ..domain.errors import UnknownStepError
from ..domain.lesson import INDEX_NAMES
from ..domain.plan import PlanSummary, parse_json_plan
from ..domain.write_cost import WriteCost, median_cost, parse_write_cost
from .logging import fields
from .postgres import scalar, session
from .settings import PostgresSettings
from .sql_script import run_file
```

Eight imports from inside the package. From `domain`: `UnknownStepError` (raised for a step the lesson does not have), `INDEX_NAMES` (the names of the lesson's indexes), the plan summary and its JSON parser, and the write-cost value, its median function and its parser. From the same package: `fields` (to attach key and value pairs to log lines), `scalar` (runs a query and returns its one value) and `session` (opens a connection for a block of code), the `PostgresSettings` class, and `run_file` (runs a whole SQL file).

`src/slow_queries/infrastructure/health_probes.py`, lines 1 to 1:

```python
"""Adapter: the health check of the one dependency, PostgreSQL."""
```

The docstring: the health check of the one dependency, PostgreSQL.

`src/slow_queries/infrastructure/health_probes.py`, lines 7 to 8:

```python
from ..application.health import ProbeFailedError
from .postgres import scalar, session
```

`ProbeFailedError` is the lab's own error for "this dependency is not usable", raised so that callers never see a driver-specific error. `scalar` and `session` are the two connection helpers described above.

## Try it yourself

1. `.venv/bin/python` starts an interactive session. Type `from slow_queries.domain.host import HostLoad; HostLoad(40.0, 12).note()` and press Enter: it prints the "Measured on a loaded machine..." sentence. Try `HostLoad(2.0, 12).note()` for the quiet version. Exit with Ctrl-D.
2. `.venv/bin/python -c "from slow_queries.domain.plan import parse_text_plan; print(parse_text_plan(open('sql/explain/q1_day_before.txt').read().splitlines()))"` prints a `PlanSummary(execution_ms=..., pages=..., node_types=('Seq Scan', ...), ...)` for the committed plan.
3. `.venv/bin/python -c "from slow_queries.domain.comparison import Improvement as I; from slow_queries.domain.plan import parse_text_plan as p; r=lambda n: p(open(f'sql/explain/{n}.txt').read().splitlines()); print(round(I(r('q1_day_before'), r('q1_day_after')).speedup))"` prints the speed-up of the day query (a few hundred).
4. `make test` runs the unit tests of these modules without a database.

## Mistakes people make

- Mixing tabs and spaces for indentation.
- Using a mutable default (`def f(x=[])`): the same list is shared by every call.
- Comparing with `is` where `==` was meant.
- Forgetting that a `list` assigned to a second name is the same list.
- Catching `Exception` and hiding bugs.
- Using `==` to compare floats exactly.

**How this repository avoids them.** Defaults are never mutable (`lambda` defaults and tuples instead of lists). Errors are specific classes, never a bare `Exception`. Dataclasses are frozen. Division is guarded with `max(...)`. Every module has a docstring (ruff `D100`).

## Check yourself

1. What does `if __name__ == "__main__":` guard? *Code that must run only when the file is started as a program, not when imported.*
2. What does the `*` in `def f(a, *, b)` mean? *Everything after it, here `b`, can only be passed by name.*
3. What does `with open(path) as f:` guarantee? *The file is closed when the block ends, also if an error is raised.*
4. What is the difference between a list and a tuple? *A list can be changed after creation; a tuple cannot.*
5. What does `raise Error("x") from cause` add? *It records `cause` as the original reason, so the traceback shows both.*

## Further reading

- The Python Tutorial (3.13): https://docs.python.org/3.13/tutorial/index.html
- Language Reference, "Compound statements" and "Expressions": https://docs.python.org/3.13/reference/index.html
- This repository requires Python 3.12 or newer (`requires-python = ">=3.12"`) and was run on 3.13.12; CI uses 3.12.

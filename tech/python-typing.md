# Python type hints

## What it is

A **type hint** is a note in the code saying what kind of value a name, parameter or result should be: `def area(width: float, height: float) -> float:`. Python itself ignores hints when it runs the program. Separate tools, **type checkers** such as mypy, read them and report mismatches before the program runs. Hints also document the code for the next reader.

## Why this repository uses it

Every function in `src/` and `tests/` is typed and `mypy --strict` checks them in `make lint`. The typed *ports* in `application/ports.py` are also how the use cases name what they need from the database without importing it.

## Where it appears

| File | What it shows |
|---|---|
| `application/ports.py` | Three `Protocol` classes: `LabDatabase`, `ArtifactStore`, `HealthProbe`. |
| `infrastructure/retry.py` | A generic function, `retry[T]`. |
| `infrastructure/postgres.py` | `psycopg.Connection[Any]`, `Iterator[...]` for a context manager. |
| `application/replay.py`, `report.py` | `Callable[[str], None]`, `TYPE_CHECKING`. |
| every module | `from __future__ import annotations` and hints on every definition. |

## How it works underneath

**Basic forms.** `x: int = 3` annotates a variable. `-> str` after a function's parameters annotates its result; `-> None` means it returns nothing.

**Containers.** `list[str]` is a list of text items. `dict[str, int]` maps text to whole numbers. `tuple[str, ...]` is a tuple of any length of text; `tuple[int, str]` is a tuple of exactly two items. `set[int]`.

**Unions.** `int | None` means "a whole number or None". Older code wrote `Optional[int]`.

**Abstract types** from `collections.abc` describe what a value can do rather than what it is: `Sequence[str]` (ordered, indexable, read-only use), `Mapping[str, int]` (dict-like, read-only use), `Iterable[int]` (can be looped over), `Iterator[int]` (produces values one at a time), `Callable[[str, int], bool]` (a function taking text and a number, returning a bool). Taking the abstract type as a parameter makes a function accept more kinds of arguments.

**`Any`** switches checking off for that value.

**Generics.** A function that works for any type but keeps the relationship between input and output uses a **type variable**: since Python 3.12, `def first[T](items: Sequence[T]) -> T:` declares `T` right after the name. If you pass `Sequence[str]` the result is `str`.

**Protocols (structural typing).** `class Reader(Protocol): def read(self) -> str: ...` describes a shape. *Any* class that has a matching `read` method counts as a `Reader`, without inheriting from it. This is how code can depend on an "interface" while the real classes stay independent.

**Forward references and `from __future__ import annotations`.** With this line at the top of a file, hints are not evaluated when the file loads; they stay as text. A class can then be named inside its own definition, and hints cost nothing at start-up.

**`TYPE_CHECKING`.** A constant that is `False` when the program runs and `True` for type checkers. Imports placed under `if TYPE_CHECKING:` exist only for hints, which avoids circular imports.

**`# type: ignore`** silences the checker on one line; it should be rare and explained.

**Libraries without hints** can hurt checking; most popular libraries ship hints (a `py.typed` marker) or have a separate package of stubs (`types-requests`).

## Walkthrough of this repository's use

### The ports

`src/slow_queries/application/ports.py`, lines 1 to 62:

```python
"""Ports: what the use cases need from the outside world. Adapters in `infrastructure` implement them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from ..domain.write_cost import WriteCost


class LabDatabase(Protocol):
    """The orders table as the lesson changes it, one index at a time."""

    def reset_to(self, step: int) -> None:
        """Put the table in the state after migration `step` (0: only the primary key). Refreshes statistics."""
        ...

    def apply_step(self, number: int) -> None:
        """Apply migration `number` and refresh statistics. Raises `UnknownStepError` for a number the lesson lacks."""
        ...

    def capture_plan(self, name: str) -> tuple[str, ...]:
        """Run `explain/<name>.sql` once to warm the cache, again to measure, and return the measured plan's lines."""
        ...

    def measure_write_cost(self, repetitions: int) -> WriteCost:
        """The median cost of inserting 10,000 orders with the indexes now in place; the inserts are rolled back."""
        ...

    def vacuum(self) -> None:
        """Vacuum the orders table, so the visibility map and free space are current."""
        ...

    def row_count(self) -> int:
        """Rows in the orders table."""
        ...

    def index_sizes(self) -> Mapping[str, int]:
        """Size in bytes of each index of the orders table, by name."""
        ...


class ArtifactStore(Protocol):
    """Where the replay leaves its evidence: the captured plans and the results notes."""

    def save_plan(self, name: str, lines: Sequence[str]) -> None:
        """Keep the plan next to its query."""
        ...

    def save_report(self, text: str) -> None:
        """Keep the results notes."""
        ...


class HealthProbe(Protocol):
    """A dependency's health check."""

    name: str

    def check(self) -> str:
        """Return a short description of what is healthy. Raise `ProbeFailedError` when it is not."""
        ...
```

- Line 3 `from __future__ import annotations` (explained above). Line 5 imports `Mapping` and `Sequence`; line 6 imports `Protocol`; line 8 imports `WriteCost` from the domain, which is allowed: application may import domain.
- `class LabDatabase(Protocol):` is a **protocol class**. It lists the methods the replay needs. The `...` (Ellipsis) as the body means "no implementation here"; the real code is in `infrastructure/lab_database.py`, whose class `PostgresLabDatabase` does *not* inherit from `LabDatabase`; it matches it by having methods of the same names and types, which mypy verifies wherever a `PostgresLabDatabase` is passed to `ReplayLesson`.
- `def capture_plan(self, name: str) -> tuple[str, ...]:` takes text, returns a tuple of lines.
- `def index_sizes(self) -> Mapping[str, int]:` returns a read-only mapping from index name to bytes.
- `class HealthProbe(Protocol): name: str` declares an *attribute* `name` as part of the shape, plus a `check` method. The unit tests use tiny classes with just these two to stand in for a database (the pytest note).

### A generic function

`src/slow_queries/infrastructure/retry.py`, lines 10 to 20:

```python
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
```

`def retry[T](...)` declares a type variable `T`. `operation: Callable[[], T]` is a function taking no arguments and returning a `T`; the result of `retry` is also a `T`. So `retry(open_connection, ...)` has the type that `open_connection` returns. `retry_on: tuple[type[BaseException], ...]` is a tuple of error *classes* (`type[...]` means "the class itself, not an instance"). `sleep: Callable[[float], None] = time.sleep` has a default of the real `time.sleep`, which tests replace. `rng: random.Random | None = None` is "a random generator or nothing". `on_retry: Callable[[int, BaseException], None] | None` is an optional function receiving the attempt number and the error. The bare `*` makes everything after `operation` keyword-only.

### Hints for a context manager

`src/slow_queries/infrastructure/postgres.py`, lines 48 to 55:

```python
@contextmanager
def session(settings: PostgresSettings, *, autocommit: bool = True) -> Iterator[psycopg.Connection[Any]]:
    """A connection that is always closed, also when the block raises."""
    connection = connect(settings, autocommit=autocommit)
    try:
        yield connection
    finally:
        connection.close()
```

A function decorated with `@contextmanager` that `yield`s once is annotated as returning `Iterator[psycopg.Connection[Any]]`: the type of what it yields. `psycopg.Connection[Any]` is a generic class; `Any` says "I do not constrain what rows look like".

### Callable defaults and TYPE_CHECKING

`src/slow_queries/application/replay.py`, lines 34 to 43:

```python
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
```
`src/slow_queries/application/report.py`, lines 1 to 12:

```python
"""The results notes: a pure function from what was measured to Markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain import lesson
from ..domain.comparison import Improvement

if TYPE_CHECKING:
    from .replay import LessonResult

```

`progress: Callable[[str], None] = lambda _message: None` is a function taking text and returning nothing, with a do-nothing default. In `report.py` the import of `LessonResult` happens only under `if TYPE_CHECKING:`, because `replay.py` imports `report.py` and importing back at run time would loop. With `from __future__ import annotations`, the hint `result: LessonResult` is never evaluated, so the name needs not exist at run time.

### Optional values

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

`-> Settings | None` makes callers handle the failure case; mypy rejects code that uses the result without checking `None` first (`if settings is None: return 2` in the commands).

## Try it yourself

1. `.venv/bin/mypy` — checks all of `src` and `tests`; prints `Success: no issues found in N source files`.
2. Make a deliberate mistake: in `src/slow_queries/domain/host.py` change `def loaded(self) -> bool:` to `-> str` and run `.venv/bin/mypy`. It reports `src/slow_queries/domain/host.py:18: error: Incompatible return value type (got "bool", expected "str")  [return-value]` and `Found 1 error in 1 file`. Undo with `git checkout src/slow_queries/domain/host.py`.
3. `.venv/bin/python -c "from slow_queries.application.ports import LabDatabase; print(LabDatabase.__mro__)"` shows that `LabDatabase` is a `Protocol` class.
4. `.venv/bin/python -c "import typing, slow_queries.infrastructure.retry as r; print(r.retry.__type_params__)"` prints `(T,)`, the type parameter.

## Mistakes people make

- Thinking hints are enforced at run time.
- Using `Any` to make an error go away.
- Annotating a parameter with a concrete `list` when a `Sequence` would do.
- Returning `None` in some branches of a function annotated with a non-optional result.
- Using a mutable `list` default under the hint `list[int]`.

**How this repository avoids them.** `mypy --strict` refuses untyped definitions and unexplained `Any`. The ports are small. The one generic function is covered by tests. `# type: ignore` is not used in `src/`.

## Check yourself

1. Does Python stop a program that passes text where `int` was hinted? *No; only a type checker reports it.*
2. What does `tuple[str, ...]` mean? *A tuple of any length whose items are text.*
3. What is a Protocol? *A description of required methods; any class with those methods matches it without inheriting.*
4. Why would you put an import under `if TYPE_CHECKING:`? *The import is only needed for hints, and skipping it at run time avoids circular imports and start-up cost.*
5. What does `def f[T](x: T) -> T` declare? *A function generic in `T`: whatever type goes in, the same type comes out.*

## Further reading

- Typing documentation (Python 3.13 `typing` module): https://docs.python.org/3.13/library/typing.html
- The typing specification and tutorial: https://typing.python.org/en/latest/
- PEP 695 (type parameter syntax, Python 3.12): https://peps.python.org/pep-0695/

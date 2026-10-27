# JSON

## What it is

**JSON** (JavaScript Object Notation) is a text format for structured data that almost every language and tool can read and write. It is the usual format for data sent between programs.

## Why this repository uses it

PostgreSQL can describe a query plan as a JSON document, which is much easier to read reliably than the indented text; the integration tests use it. The logging module also uses `json.dumps` as a small, correct way to quote values.

## Where it appears

| File | Use |
|---|---|
| `src/slow_queries/domain/plan.py` | `parse_json_plan` reads the JSON form of a plan. |
| `src/slow_queries/infrastructure/lab_database.py` | `explain_json` asks PostgreSQL for `FORMAT JSON`. |
| `src/slow_queries/infrastructure/logging.py` | `json.dumps(text)` quotes log values. |
| `tests/unit/domain/test_plan.py` | JSON plans written as Python dictionaries. |

## How it works underneath

A JSON text holds one **value**, which is one of:

- an **object**: `{"name": "orders", "pages": 12}`: curly braces around `"key": value` pairs separated by commas; keys are always double-quoted text;
- an **array**: `[1, 2, 3]`: square brackets around values separated by commas;
- a **string**: `"text"` in double quotes, with `\"` and `\n` escapes;
- a **number**: `12`, `-3.5`, `1e6`;
- `true`, `false`, `null`.

There are no comments and no trailing commas. In Python, the standard module `json` converts: `json.loads(text)` turns JSON text into Python values (objects become `dict`, arrays `list`, strings `str`, numbers `int` or `float`, `null` becomes `None`) and `json.dumps(value)` does the reverse. `json.dumps("two words")` gives `"two words"` including the quotes, which is also a handy way to quote a string.

**JSON Lines (`.jsonl`)** puts one complete JSON object on each line of a file, which suits logs and measurements that are appended over time.

PostgreSQL can return query results as JSON: `EXPLAIN (FORMAT JSON)` returns the plan as a JSON document, and the `psycopg` driver decodes a `json` column into Python lists and dictionaries by itself.

## Walkthrough of this repository's use

`src/slow_queries/infrastructure/lab_database.py`, lines 74 to 78:

```python
    def explain_json(self, query: str) -> PlanSummary:
        """Plan a query with real timings and buffers and summarize it."""
        with session(self._settings) as connection:
            document: dict[str, Any] = scalar(connection, "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)[0]
        return parse_json_plan(document)
```

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) <query>` returns one row with one column: a JSON array with one element, the plan document. psycopg decodes it to Python (a `list` containing a `dict`), so `scalar(...)` gives the list and `[0]` the dictionary.

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

This is what the dictionary looks like, reduced to the keys the code reads: the top-level `"Execution Time"` and `"Plan"`; inside `"Plan"` the `"Node Type"`, the buffer counters `"Shared Hit Blocks"` and `"Shared Read Blocks"`, and the child nodes under `"Plans"` (a list of dictionaries), each with its own `"Node Type"`, optionally `"Index Name"` and `"Rows Removed by Filter"`.

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

`_json_nodes` walks the tree (a generator that calls itself on each child in `"Plans"`); `parse_json_plan` collects the facts with comprehensions. `node.get("Plans", [])` is the safe way to read an optional key. Missing keys raise `KeyError`, which is turned into a `PlanParseError`.

`src/slow_queries/infrastructure/logging.py`, lines 12 to 14:

```python
def _quote(value: object) -> str:
    text = str(value)
    return json.dumps(text) if not text or any(char in text for char in ' ="\n') else text
```

`json.dumps(text)` returns the text wrapped in double quotes with special characters escaped; used here only when a log value contains a space, an equals sign, a double quote or a line break.

## Try it yourself

(After `make up db`.)

1. `docker compose exec db psql -U lab -d lab -t -A -c "explain (analyze, buffers, format json) select count(*) from orders where customer_id = 7"` prints the JSON document; look for `"Node Type"`, `"Plans"`, `"Shared Hit Blocks"`.
2. `.venv/bin/python -c "import json; print(json.dumps('two words'), json.dumps('plain'))"` prints `"two words" "plain"`.
3. `.venv/bin/python -c "import json; d=json.loads('{\"Plan\": {\"Node Type\": \"Limit\"}}'); print(d['Plan']['Node Type'], d.get('Execution Time'))"` prints `Limit None`.

## Mistakes people make

- Single quotes or unquoted keys (not valid JSON).
- A trailing comma after the last item.
- Expecting dates: JSON has no date type, only text.
- Reading a JSON number as exact when it is a float.
- Indexing a missing key without a fallback (`d["x"]` raises `KeyError`; `d.get("x")` returns `None`).

**How this repository avoids them.** JSON is read with `json`/psycopg, never with regular expressions; optional keys use `.get`; a wrong shape becomes a named `PlanParseError`.

## Check yourself

1. What are the two container types in JSON? *Objects (key-value pairs in braces) and arrays (lists in brackets).*
2. How does Python represent a JSON object? *As a `dict`.*
3. What does `json.dumps("a b")` return? *The text `"a b"` including the double quotes.*
4. Is `{'a': 1}` valid JSON? *No; keys and strings need double quotes.*
5. What is JSON Lines? *A file with one JSON object per line.*

## Further reading

- ECMA-404 / json.org: https://www.json.org/json-en.html
- Python `json` module: https://docs.python.org/3.13/library/json.html

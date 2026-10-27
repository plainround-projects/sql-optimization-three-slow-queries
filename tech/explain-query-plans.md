# EXPLAIN and reading query plans

## What it is

A **query plan** is the step-by-step method PostgreSQL chooses to answer an SQL statement: which tables to read, in what way, which indexes to use, how to sort and combine. **`EXPLAIN`** prints the plan instead of (or as well as) running the statement. Reading plans is the central skill of this lesson: a plan tells you *why* a query is slow.

## Why this repository uses it

Reading plans is the lesson. Every claim of the README ("the day query was a full scan that threw away 997,252 rows", "the covering index touches 506 pages, not 1,009") is a line of a plan that you can open. The Python code parses those same plans to check the claims automatically.

## Where it appears

| File | Role |
|---|---|
| `sql/explain/*.sql` (11 files) | The `EXPLAIN` statement for each query. |
| `sql/explain/*.txt` (11 files) | The captured output, rewritten by `make run`. |
| `sql/explain/results.md` | The table the replay builds from the plans. |
| `src/slow_queries/domain/plan.py` | Reads the text and JSON forms. |
| `src/slow_queries/domain/write_cost.py` | Reads the `WAL:` line of an insert plan. |
| `src/slow_queries/infrastructure/lab_database.py` | `capture_plan`, `explain_json`, `measure_write_cost`. |

## How it works underneath

**Variants.**

- `EXPLAIN SELECT ...` shows the plan the planner *would* use, with **estimates** (a guess based on statistics). The statement is not run.
- `EXPLAIN ANALYZE SELECT ...` **runs** the statement and adds **actual** numbers. Because it really executes, an `INSERT`, `UPDATE` or `DELETE` really happens; wrap it in a transaction and `ROLLBACK` to undo.
- Options go in brackets: `EXPLAIN (ANALYZE, BUFFERS, WAL, SERIALIZE, FORMAT JSON) ...`.
  - `BUFFERS` adds page counts: `shared hit=` (found in PostgreSQL's cache), `read=` (not found there, fetched from the operating system or disk), `dirtied=`, `written=`.
  - `WAL` adds write-ahead-log volume for statements that write: `WAL: records=... bytes=...`.
  - `SERIALIZE` (PostgreSQL 17 and newer) also measures the work of converting the result rows to the text sent to the client, including fetching out-of-line (TOAST) values; it adds a `Serialization:` line.
  - `FORMAT JSON` prints the same information as a JSON document, which programs parse easily.

**A plan is a tree.** The text is indented: the top line is the last step, which produces the result; lines starting with `->` are child steps feeding it. Data flows from the deepest steps up. Each step is a **node**.

**What each node line says.**

```text
Seq Scan on orders  (cost=0.00..78758.28 rows=5003 width=457) (actual time=0.455..830.145 rows=2748.00 loops=1)
```

- `Seq Scan on orders`: the node type and the table.
- `cost=0.00..78758.28`: the planner's estimate in arbitrary cost units: before the first row, and for all rows.
- `rows=5003`: *estimated* rows out of this node. `width=457`: estimated bytes per row.
- `actual time=0.455..830.145`: milliseconds until the first row and until the last row.
- `rows=2748.00`: *actual* rows (PostgreSQL 18 prints a fraction). If this differs by a lot from the estimate, the statistics are poor.
- `loops=1`: how many times the node ran; times and rows are per loop.

**Lines under a node.** `Filter:` (a condition applied to each row after reading it), `Rows Removed by Filter:` (rows read and thrown away: a high number is wasted work), `Index Cond:` (a condition handled by the index), `Recheck Cond:`, `Sort Key:`, `Sort Method:` (`quicksort`, `top-N heapsort`: keeping only the best N rows, `external merge`: spilled to disk), `Heap Blocks:`, `Heap Fetches:` (table visits made by an index-only scan), `Index Searches:` (how many separate descents of the index tree; PostgreSQL 18), `Buffers:`, `I/O Timings:` (time waiting for reads; needs `track_io_timing = on`).

**The footer.** `Planning Time:` (time choosing the plan), `Serialization:` (time and size of the output), `Execution Time:` (total, in milliseconds).

**How to read one.**

1. Start at the deepest node: how is the table read (`Seq Scan`, `Index Scan`...)?
2. Compare estimated and actual rows at each node.
3. Look for wasted work: `Rows Removed by Filter`, a `Sort` where an index could provide order, large `Buffers`.
4. Compare *pages touched* (hit + read), which does not depend on the machine's speed, as well as milliseconds, which does.

## Walkthrough of this repository's use

### The `.sql` files

`sql/explain/q1_day_before.sql`, lines 1 to 4:

```sql
-- Query 1 before: date(created_at) wraps the column, so no index on created_at can be used.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE date(created_at) = '2026-03-14';
```
`sql/explain/q3_toast_wide.sql`, lines 1 to 4:

```sql
-- Why a big text column costs: SELECT * on 20,000 rows whose 5 KB note is stored out of line (TOAST).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT * FROM order_notes_demo WHERE customer_id = 7 AND created_at < '2026-02-01';
```

Each file is a comment, `SET timezone = 'UTC'` (so the date literal means the same on every machine), the `EXPLAIN` with options, and the query. Most use `EXPLAIN (ANALYZE, BUFFERS)`. The TOAST one adds `SERIALIZE`, because the cost of fetching the 5 kB notes is paid when the rows are converted for the client, not in the scan.

### Reading `q1_day_before.txt` line by line

`sql/explain/q1_day_before.txt`, lines 1 to 7:

```text
Seq Scan on orders  (cost=0.00..78758.28 rows=5003 width=457) (actual time=0.455..830.145 rows=2748.00 loops=1)
  Filter: (date(created_at) = '2026-03-14'::date)
  Rows Removed by Filter: 997252
  Buffers: shared hit=2058 read=61692
  I/O Timings: shared read=448.925
Planning Time: 0.130 ms
Execution Time: 831.496 ms
```

1. The only node is `Seq Scan on orders`. Estimated 5,003 rows, 457 bytes each; actually 2,748 rows in 830 ms. The estimate is off by almost 2: the planner does not know the selectivity of `date(created_at) = ...` because the function hides the column from its statistics, so it uses a fixed guess.
2. `Filter: (date(created_at) = '2026-03-14'::date)` is the test applied to every row.
3. `Rows Removed by Filter: 997252` is the wasted work: 1,000,000 rows read, 2,748 kept.
4. `Buffers: shared hit=2058 read=61692` is 63,750 pages in all.
5. `I/O Timings: shared read=448.925` is 449 ms of the 830 spent waiting for pages (shown because `track_io_timing` is on in the compose file).
6. `Planning Time` and `Execution Time` close the plan.

### Reading the fixed plan

`sql/explain/q2_latest_whale_after.txt`, lines 1 to 8:

```text
Limit  (cost=0.42..37.18 rows=10 width=457) (actual time=0.011..0.019 rows=10.00 loops=1)
  Buffers: shared hit=13
  ->  Index Scan using idx_orders_customer_created on orders  (cost=0.42..45203.28 rows=12300 width=457) (actual time=0.010..0.018 rows=10.00 loops=1)
        Index Cond: (customer_id = 7)
        Index Searches: 1
        Buffers: shared hit=13
Planning Time: 0.060 ms
Execution Time: 0.030 ms
```

`Limit` on top: stop after 10 rows. Below it, `Index Scan using idx_orders_customer_created`: the rows come out already sorted (so no `Sort` node), the `Index Cond` is the equality on `customer_id`, `Index Searches: 1` says the tree was descended once, and `Buffers: shared hit=13` says 13 pages in all. Compare the before plan (`q2_latest_whale_before.txt`): `Sort` with `top-N heapsort` on top of a `Seq Scan` that removed 988,148 rows.

### `SERIALIZE` and TOAST

`sql/explain/q3_toast_wide.txt`, lines 1 to 10:

```text
Seq Scan on order_notes_demo  (cost=0.00..507.00 rows=2975 width=48) (actual time=0.006..1.827 rows=2975.00 loops=1)
  Filter: ((created_at < '2026-02-01 00:00:00+00'::timestamp with time zone) AND (customer_id = 7))
  Rows Removed by Filter: 17025
  Buffers: shared hit=207
Planning Time: 0.057 ms
Serialization: time=11.855 ms  output=15055kB  format=text
  Buffers: shared hit=10625
Execution Time: 13.952 ms
```

After the main plan comes `Serialization: time=11.855 ms output=15055kB format=text` and a second `Buffers: shared hit=10625` that belongs to it: reading the TOAST table to fetch the 5 kB notes of 2,975 rows. The Python function `pages_touched` adds this second line because it follows `Serialization:` (regular-expressions note).

### The write-ahead-log option

The write-cost batches run `EXPLAIN (ANALYZE, BUFFERS, WAL)` on an `INSERT` and then `ROLLBACK` (`measure_write_cost` in `lab_database.py`), because `ANALYZE` really executes the insert. The text contains a `WAL: records=... bytes=...` line which `write_cost.py` reads.

### JSON form

`src/slow_queries/domain/plan.py`, lines 85 to 98:

```python
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
```

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` returns the plan as JSON with keys such as `"Plan"`, `"Node Type"`, `"Plans"` (children), `"Index Name"`, `"Shared Hit Blocks"`, `"Rows Removed by Filter"`, `"Heap Fetches"` and `"Execution Time"`. The tests use this form (`explain_json`) because keys are easier to read reliably than text.

## Try it yourself

(After `make up db`.)

1. `cat sql/explain/q1_day_before.txt` — read the plan above in your own file.
2. `docker compose exec -T db psql -U lab -d lab < sql/explain/q1_day_before.sql` — runs the statement and prints a fresh plan.
3. `docker compose exec db psql -U lab -d lab -c "explain select * from orders where customer_id = 7 order by created_at desc limit 10"` — only the estimate, no execution time.
4. `docker compose exec db psql -U lab -d lab -c "explain (analyze, buffers, format json) select count(*) from orders"` — the JSON form.
5. `.venv/bin/python -c "from slow_queries.domain.plan import parse_text_plan; p=parse_text_plan(open('sql/explain/q3_listing_after.txt').read().splitlines()); print(p.node_types, p.heap_fetches, p.pages)"` — prints `('Index Only Scan',) 0 506`.

## Mistakes people make

- Running `EXPLAIN ANALYZE` on an `UPDATE` or `DELETE` in production without a transaction.
- Trusting one run: the first run may be slow because the cache is cold. Run twice and read the second.
- Comparing milliseconds across machines; compare ratios and page counts.
- Ignoring the estimate-versus-actual gap.
- Reading only the top line.
- Forgetting that `EXPLAIN` without `ANALYZE` does not show whether the index really helps.

**How this repository avoids them.** Plans are run twice and the second is kept; comparison tables show pages touched next to milliseconds; the results file says how busy the machine was; `ANALYZE` on inserts is always inside a transaction that is rolled back; and the parsed numbers are tested against the committed files.

## Check yourself

1. What is the difference between `EXPLAIN` and `EXPLAIN ANALYZE`? *The first shows the estimated plan without running the statement; the second runs it and adds actual times and row counts.*
2. What does `Rows Removed by Filter: 997252` tell you? *The scan read about a million rows and discarded almost all of them: wasted work an index could avoid.*
3. What do `shared hit=2058 read=61692` mean? *2,058 pages were found in PostgreSQL's cache and 61,692 were not, so they were fetched from outside it.*
4. Why prefer page counts to milliseconds when comparing two plans? *Page counts do not depend on how busy or fast the machine is.*
5. What does `SERIALIZE` add? *The cost of turning the result rows into the text sent to the client, including detoasting.*

## Further reading

- PostgreSQL 18, "Using EXPLAIN": https://www.postgresql.org/docs/18/using-explain.html
- `EXPLAIN` command reference (options): https://www.postgresql.org/docs/18/sql-explain.html

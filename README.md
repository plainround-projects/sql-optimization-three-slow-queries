# SQL optimization: three slow queries

A one-million-row `orders` table in PostgreSQL 18 with real skew, three slow queries an application might run against it, and for each one the plan before, one change, and the plan after, with the write cost of every index you add.

This repository is the runnable build of the Plainround lesson **"Read plans and fix three slow queries"** (`/prep/sql-optimization/project-three-slow-queries`, planned at **5 hours**). The lesson is in the SQL optimization track; its first topic ("How queries run") defines the PostgreSQL lab this project builds on.

## What is in it

| Piece | Where |
|---|---|
| PostgreSQL 18 in Docker | `docker-compose.yml` |
| Schema (DDL), seed (DML), the lesson's queries | `sql/001_schema.sql`, `sql/002_seed.sql`, `sql/003_queries.sql` |
| One migration per change the lesson makes | `sql/migrations/` |
| Every plan, before and after (`.sql` to run, `.txt` captured) and the numbers | `sql/explain/` |
| Script that replays the lesson and writes those files | `scripts/run_lesson.py` |
| Tests, one per "Done when" line | `tests/test_lesson.py` |
| How it fits together, and why | [ARCHITECTURE.md](ARCHITECTURE.md) |

## Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Docker with Compose v2 | Docker 24 or newer | Runs PostgreSQL. No local PostgreSQL or `psql` needed. |
| Python | 3.12 or newer | Only for `make run` and `make test`; a virtual environment is created in `.venv/`. |
| make | any | |
| PostgreSQL | **18** (`postgres:18`, tested on 18.6) | The track assumes PostgreSQL 18 as of October 2026. |

Free disk: about 1.5 GB (the table is 493 MB, the indexes about 110 MB, plus WAL). Free memory: the container asks for 512 MB of shared buffers and 1 GB of shared memory.

## Setup, run, test, stop

```bash
make up      # start PostgreSQL 18 on localhost:55431 and wait until it is healthy
```

```bash
make db      # create the schema, load 1,000,000 orders (about 30 seconds), run the queries in their slow form
```

```bash
make run     # replay the lesson: plans before, each index added in turn, plans after, write cost per index
```

```bash
make test    # 8 tests, about 15 seconds, against the database from `make db`
```

```bash
make down    # stop PostgreSQL and delete its volume
```

`make run` rewrites the `.txt` plans and `sql/explain/results.md` with your machine's timings. Page counts and plan shapes will match the ones in this README; milliseconds will not. To poke around by hand: `make psql`.

The default port is 55431 so it does not collide with a PostgreSQL you already run. Copy `.env.example` to `.env` to change it.

## What the build does

1. **Seed** a skewed `orders` table: customers 1 to 50 hold 60% of the rows (about 12,000 orders each), customers 51 to 50,000 get about eight each, and `created_at` spans the year 2026. `notes` is a deliberately wide text column. `setseed` makes the data identical on every run.
2. **Query 1, the day query.** `date(created_at) = '2026-03-14'` hides the column from any index. Rewritten as a half-open range on the raw column, with an index on `created_at`, the plan stops reading the table.
3. **Query 2, the latest orders.** One customer's ten newest orders. An index on `(customer_id, created_at DESC)` returns them with no sort step.
4. **Query 3, the wide listing.** `SELECT *` to show five columns. Naming the columns, then a covering index, then a look at what a really large text column costs.
5. **Write cost.** Insert 10,000 orders before and after each index, and keep or drop each index with a reason.

### The numbers from the committed run

These come from `sql/explain/results.md`, produced by `make run` on a 12-CPU laptop sharing Docker with other containers, so treat the milliseconds as order of magnitude.

| Query | Before | After | Pages touched, before then after |
|---|---:|---:|---:|
| Day query | 385 ms, `Seq Scan` | 4.0 ms, `Bitmap Heap Scan` on `idx_orders_created_at` (96x faster) | 63,125 then 2,713 |
| Latest 10, heavy customer | 500 ms, `Seq Scan` + top-N `Sort` | 0.026 ms, `Index Scan`, no `Sort` | 63,125 then 13 |
| Latest 10, small customer (7 orders) | 458 ms | 0.040 ms | 63,125 then 10 |
| Listing, `SELECT *` then covering index | 3.3 ms | 2.1 ms, `Index Only Scan`, `Heap Fetches: 0` | 1,009 then 506 |
| Listing, five columns, no covering index | 2.7 ms | same pages as `SELECT *` | 1,009 then 1,009 |
| TOAST demo, `SELECT *` then without the note | 37.0 ms | 3.1 ms | 10,832 then 207 |

Cost of 10,000 inserts (median of five, each rolled back):

| Index set | Pages touched | WAL records | Median ms |
|---|---:|---:|---:|
| none beyond the primary key | 31,412 | 20,330 | 90 |
| + `idx_orders_created_at` | 61,414 | 30,331 | 104 |
| + `idx_orders_customer_created` | 91,413 | 40,331 | 122 |
| + `idx_orders_listing` (covering) | 121,560 | 50,359 | 416 |
| covering only (narrow one dropped) | 91,559 | 40,362 | 277 |

Every index adds about 30,000 page touches and 10,000 WAL records per 10,000 inserts, which is the stable way to read the cost. Milliseconds are noisy.

**Keep or drop, with reasons.**
- `idx_orders_created_at`: **keep.** About 30,000 extra page touches per 10,000 inserts buys a 100-fold faster day query and any other range on time.
- `idx_orders_customer_created`: **drop** once the covering index exists. `idx_orders_listing` has the same leading columns, so it serves the latest-orders query too; keeping both pays the write cost twice for nothing (migration `004`).
- `idx_orders_listing`: **keep, but only if the listing is hot.** It is 60 MB against 30 MB for the narrow index and costs more per insert. If the listing ran rarely, keep the narrow index and skip the covering one.

## Done when: how each line is proved

The lesson has one "Done when" line per step plus the three in its diagram.

| Done when (lesson) | How to see it | Test |
|---|---|---|
| **Step 1.** A count by customer shows the intended skew and statistics are fresh. | `make db` prints the top five customers (about 12,000 orders each), the whale share (0.600) and `last_analyze`. | `test_step1_seed_has_the_intended_skew_and_fresh_statistics` |
| **Step 2.** Your notes say where the time went and whether the row estimate was close. | `sql/explain/q1_day_before.txt`: one `Seq Scan`, `Rows Removed by Filter: 997252`, 63,125 pages, estimate 5,000 rows against 2,748 actual. The planner cannot use the column's statistics through `date()`, so it falls back to a default guess. [ARCHITECTURE.md](ARCHITECTURE.md) walks the plan line by line. | `test_step2_the_function_on_the_column_forces_a_full_scan` |
| **Step 3.** The plan switches from a full scan to an index scan and the timing drops at least ten times. | Compare `q1_day_before.txt` with `q1_day_after.txt`; `sql/explain/results.md` shows the ratio. | `test_step3_day_query_uses_the_index_and_is_ten_times_faster` (asserts time and pages both drop at least 10x) |
| **Step 4.** The plan reads ten index entries without a sort step, for a small customer and the largest. | `q2_latest_whale_after.txt` and `q2_latest_small_after.txt`: `Index Scan using idx_orders_customer_created`, no `Sort`, 13 and 10 pages. | `test_step4_latest_orders_read_ten_entries_with_no_sort_for_small_and_large_customers` |
| **Step 5.** The plan reads fewer buffers or pages, and you can explain why the large text column cost so much. | `q3_listing_after.txt` (`Index Only Scan`, `Heap Fetches: 0`, 506 pages against 1,009). `q3_toast_wide.txt` against `q3_toast_narrow.txt` (10,832 pages against 207). The explanation is in [ARCHITECTURE.md](ARCHITECTURE.md). | `test_step5_covering_index_gives_an_index_only_scan_with_fewer_pages`, `test_step5_a_big_out_of_line_column_costs_pages_only_when_it_is_selected` |
| **Step 6.** The notes record the write cost of each index and you keep or drop each with a reason. | The write-cost table in `sql/explain/results.md` and the keep-or-drop list above. | `test_step6_each_index_adds_write_work_and_the_batches_are_rolled_back` |
| **Diagram.** Day query at least ten times faster; latest orders without a sort step; write cost of each index recorded. | The three rows above. | |

One more test, `test_the_captured_plans_in_the_repository_match_the_story`, checks that the committed `.txt` plans say what this README says they do.

## Stretch goals

| Stretch | Built? |
|---|---|
| Run the same three fixes on MySQL and compare the plans' wording | No. The lesson allows either engine; this build is PostgreSQL only. |
| A partial index for the rare `status = 'failed'` rows, and when the planner uses it | No. Here `failed` is a quarter of the rows, not rare, so the exercise needs a different seed. |
| Make a query slow again with a type mismatch between column and parameter | No. |

Ideas for each are in the "How to extend it" section of [ARCHITECTURE.md](ARCHITECTURE.md).

## What is simplified for teaching

- **One engine, one machine.** PostgreSQL 18 in a single container, no replicas, no connection pool.
- **The lesson's "notes" column is inline, not TOASTed.** 420 bytes a row is below the roughly 2 KB at which PostgreSQL moves a value out of line, so naming five columns instead of `SELECT *` does not change the pages read here. The `order_notes_demo` table (20,000 rows with a 5 KB note) exists to show the TOAST effect the lesson describes.
- **The day query's estimate is 5,000 rows, not 1.** The lesson's sample plan shows 1; PostgreSQL 18 applies a default selectivity to a function it cannot see through. The point (the estimate is a guess, far from the 2,748 actual) is the same.
- **Parallel query is off** (`max_parallel_workers_per_gather = 0`, as in the track's lab) so plans have no `Gather` nodes.
- **Write cost is measured with rolled-back batches** under `EXPLAIN (ANALYZE, BUFFERS, WAL)`, with one warm-up, so the table does not grow between runs.
- **Throwaway credentials** (`lab`/`lab`) on a port that only your machine can reach. Do not reuse them anywhere.
- The seed uses `setseed`, so the data repeats; real data would not.

## Troubleshooting

- `port is already allocated`: another process uses 55431. Set `PGPORT` in `.env` and run `make down && make up`.
- `make test` fails with a connection error: run `make up` and `make db` first.


## Author and license

Written by Sumit Srivastava. Released under the MIT License, see [LICENSE](LICENSE).

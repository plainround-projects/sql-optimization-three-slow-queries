# SQL optimization: three slow queries

A one-million-row `orders` table in PostgreSQL 18 with real skew, three slow queries an application might run against it, and for each one the plan before, one change, and the plan after, with the write cost of every index you add.

This repository is the runnable build of the Plainround lesson **"Read plans and fix three slow queries"** (`/prep/sql-optimization/project-three-slow-queries`, planned at **5 hours**). The lesson is in the SQL optimization track; its first topic ("How queries run") defines the PostgreSQL lab this project builds on.

## Architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/architecture-dark.svg">
  <img alt="The run_cli command starts ReplayLesson, which reads plans and applies migrations through the lab_database adapter and writes the notes file through the ArtifactStore port. The adapter runs EXPLAIN and rolled-back inserts against the orders table and applies the index migrations 001 to 004. A seed script loads one million rows." src="docs/diagrams/architecture.svg">
</picture>

Notice that the table and the indexes live in PostgreSQL while the replay logic stays in the package behind two ports; amber marks the plan before any index.

## How one run flows

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/flow-dark.svg">
  <img alt="One make run in five steps. ReplayLesson resets the table, reads the slow plans, adds one index at a time while timing 10,000 rolled-back inserts, and writes results.md. Amber rows are the slow scan and the write cost of each index." src="docs/diagrams/flow.svg">
</picture>

The run ends with the notes file, whose headline row shows the heavy-customer query going from 542.699 ms to 0.030 ms.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker with Compose v2 | Docker 24 or newer | Runs PostgreSQL. No local PostgreSQL or `psql` needed. |
| Python | 3.12 or newer | Runs the replay, the health command and the tests in a virtual environment (`.venv/`, built from the hashed lock file). |
| make | any | |
| PostgreSQL | **18** (`postgres:18`, tested on 18.6) | The track assumes PostgreSQL 18 as of October 2026. |
| Python packages | `psycopg` 3 (runtime) | Dev tools: pytest, pytest-cov, ruff, mypy, import-linter, pip-audit. All pinned with hashes in `requirements.lock` and `requirements-dev.lock`. |

Free disk: about 1.5 GB (the table is 493 MB, the indexes about 110 MB, plus WAL). Free memory: the container asks for 512 MB of shared buffers and 1 GB of shared memory.

## Setup, run, test, stop

```bash
make up      # create .env from .env.example if needed, start PostgreSQL 18 on localhost:55431, wait until it is healthy
```

```bash
make db      # schema, 1,000,000 skewed orders (about 30 seconds the first time), the lesson's queries; safe to run again
```

```bash
make run     # replay the lesson: plans before, each index added in turn, plans after, write cost per index
```

```bash
make test    # unit tests with coverage (no database); domain and application must stay at 95% or more
```

```bash
make test-integration test-e2e   # the lesson's outcomes and the whole replay, against the seeded database
```

```bash
make lint    # ruff check and format check, mypy --strict, import-linter
```

```bash
make down    # stop PostgreSQL and delete its volume
```

Other targets (`make help` lists all): `make health` (exit 0 when the seeded table is there), `make reset` (drop the lab's tables so `make db` rebuilds them), `make audit` (check the locked dependencies for known vulnerabilities), `make psql`, `make docker-build`.

`make run` rewrites the `.txt` plans and `sql/explain/results.md` with your machine's numbers and says at the top how busy the machine was. Page counts and plan shapes will match the ones below; milliseconds will not. The default port is 55431 so it does not collide with a PostgreSQL you already run; copy `.env.example` to `.env` and edit it to change that.

## Project structure

```text
.
├── docker-compose.yml        PostgreSQL 18 (init process, health check over TCP, parallel query off)
├── Dockerfile                the command-line programs as an image (non-root, pinned base)
├── Makefile                  up, db, run, test, lint, down and the rest
├── pyproject.toml            package, tool configuration, import-linter contracts
├── requirements*.lock        hashed, pinned dependencies
├── sql/                      everything that runs in the database
│   ├── 001_schema.sql        DDL (IF NOT EXISTS, one transaction)
│   ├── 002_seed.sql          DML (skips tables that already have rows)
│   ├── 003_queries.sql       every query the lesson runs, each with a one-line comment
│   ├── reset.sql             drop the lab's tables
│   ├── migrations/           one idempotent, transactional file per index; down/ holds the undo scripts
│   ├── bench/                the 10,000-row insert batch the write-cost measurement runs
│   └── explain/              each query's EXPLAIN (ANALYZE, BUFFERS) as .sql, the captured .txt, and results.md
├── src/slow_queries/
│   ├── domain/               plan parsing, write cost, comparisons, the lesson's steps: pure, depends on nothing
│   ├── application/          the replay use case, the report, the health use case, and the ports they need
│   ├── infrastructure/       PostgreSQL adapter, SQL file runner, settings, logging, retry, shutdown
│   └── interfaces/           the replay and health commands
├── tests/
│   ├── unit/                 domain, application, infrastructure and interface tests with in-memory fakes
│   ├── integration/          the lesson's outcomes against the seeded database
│   └── e2e/                  the whole replay through the command-line program
└── docs/adr/                 decision records
```

The dependency rule: `domain` imports nothing from this package; `application` imports `domain`; `infrastructure` imports both; `interfaces` imports all three; nothing imports `interfaces`. `make lint` enforces it with import-linter, and a second contract keeps `psycopg` out of `domain` and `application`. The pattern is ports and adapters; [ARCHITECTURE.md](ARCHITECTURE.md) says why.

## What the build does

1. **Seed** a skewed `orders` table: customers 1 to 50 hold 60% of the rows (about 12,000 orders each), customers 51 to 50,000 get about eight each, and `created_at` spans the year 2026. `notes` is a deliberately wide text column. `setseed` makes the data identical on every run.
2. **Query 1, the day query.** `date(created_at) = '2026-03-14'` hides the column from any index. Rewritten as a half-open range on the raw column, with an index on `created_at`, the plan stops reading the table.
3. **Query 2, the latest orders.** One customer's ten newest orders. An index on `(customer_id, created_at DESC)` returns them with no sort step.
4. **Query 3, the wide listing.** `SELECT *` to show five columns. Naming the columns, then a covering index, then a look at what a really large text column costs.
5. **Write cost.** Insert 10,000 orders before and after each index, and keep or drop each index with a reason.

### What the committed run shows

From `sql/explain/results.md`. **The committed run was measured on a loaded machine** (a shared laptop with a load average of 19.8 on 12 CPUs, see the first lines of the file): its milliseconds are several times higher than on a quiet machine, so read the **ratios and the page counts**, which survive load; rerun `make run` for clean milliseconds.

| Query | Plan before | Plan after | Pages touched, before then after |
|---|---|---|---:|
| Day query | `Seq Scan`, 997,252 rows discarded by the filter | `Bitmap Heap Scan` on `idx_orders_created_at`: about 300 times faster (831 ms then 2.7 ms in this run) | 63,750 then 2,713 |
| Latest 10, heavy customer | `Seq Scan` + top-N `Sort` | `Index Scan`, no `Sort`: thousands of times faster (543 ms then 0.03 ms) | 63,750 then 13 |
| Latest 10, small customer (7 orders) | `Seq Scan` + `Sort` | `Index Scan`, no `Sort` | 63,750 then 10 |
| Listing, `SELECT *` then covering index | `Bitmap Heap Scan` + `Sort`, 1,010 rows | `Index Only Scan`, `Heap Fetches: 0` | 1,009 then 506 |
| Listing, five columns, no covering index | same pages as `SELECT *` | not different: the notes are inline here | 1,009 then 1,009 |
| TOAST demo, `SELECT *` then without the note | the 5 KB note is fetched from the TOAST table | the TOAST table is never read | 10,832 then 207 |

Cost of 10,000 inserts (median of five, each rolled back); pages and WAL records are the stable figures:

| Index set | Pages touched | WAL records |
|---|---:|---:|
| none beyond the primary key | 31,547 | 20,357 |
| + `idx_orders_created_at` | 61,548 | 30,357 |
| + `idx_orders_customer_created` | 91,548 | 40,357 |
| + `idx_orders_listing` (covering) | 121,561 | 50,359 |
| covering only (narrow one dropped) | 91,560 | 40,359 |

Every index adds about 30,000 page touches and 10,000 WAL records per 10,000 inserts. Index sizes at the end: `idx_orders_created_at` 22.5 MB, `idx_orders_listing` 59.7 MB (the narrow `(customer_id, created_at)` index is dropped by then).

**Keep or drop, with reasons.**
- `idx_orders_created_at`: **keep.** About 30,000 extra page touches per 10,000 inserts buys a day query hundreds of times faster, and any other range on time.
- `idx_orders_customer_created`: **drop** once the covering index exists. `idx_orders_listing` has the same leading columns, so it serves the latest-orders query too; keeping both pays the write cost twice for nothing (migration `004`).
- `idx_orders_listing`: **keep, but only if the listing is hot.** It is twice the size of the narrow index and costs more per insert. If the listing ran rarely, keep the narrow index and skip the covering one.

## Done when: how each line is proved

The lesson has one "Done when" line per step plus the three in its diagram. The tests marked integration run against the seeded database (`make test-integration`).

| Done when (lesson) | How to see it | Test |
|---|---|---|
| **Step 1.** A count by customer shows the intended skew and statistics are fresh. | `make db` prints the top five customers (about 12,000 orders each), the whale share (0.600) and `last_analyze`; `make health` says `1,000,000 orders, statistics fresh`. | `test_the_seed_has_the_intended_skew_and_fresh_statistics` |
| **Step 2.** Your notes say where the time went and whether the row estimate was close. | `sql/explain/q1_day_before.txt`: one `Seq Scan`, `Rows Removed by Filter: 997252`, 63,750 pages, estimate 5,000 rows against 2,748 actual. The planner cannot use the column's statistics through `date()`, so it falls back to a default guess. [ARCHITECTURE.md](ARCHITECTURE.md) walks the plan line by line. | `test_a_function_on_the_column_forces_a_full_scan_that_discards_almost_every_row` |
| **Step 3.** The plan switches from a full scan to an index scan and the timing drops at least ten times. | Compare `q1_day_before.txt` with `q1_day_after.txt`; `results.md` shows the ratio. | `test_the_day_query_uses_the_index_and_is_ten_times_faster` (asserts time and pages both drop at least 10x) |
| **Step 4.** The plan reads ten index entries without a sort step, for a small customer and the largest. | `q2_latest_whale_after.txt` and `q2_latest_small_after.txt`: `Index Scan using idx_orders_customer_created`, no `Sort`, 13 and 10 pages. | `test_latest_orders_read_ten_index_entries_with_no_sort_for_heavy_and_small_customers` |
| **Step 5.** The plan reads fewer buffers or pages, and you can explain why the large text column cost so much. | `q3_listing_after.txt` (`Index Only Scan`, `Heap Fetches: 0`, 506 pages against 1,009). `q3_toast_wide.txt` against `q3_toast_narrow.txt` (10,832 pages against 207). The explanation is in [ARCHITECTURE.md](ARCHITECTURE.md). | `test_a_covering_index_gives_an_index_only_scan_with_fewer_pages`, `test_a_big_out_of_line_column_costs_pages_only_when_it_is_selected` |
| **Step 6.** The notes record the write cost of each index and you keep or drop each with a reason. | The write-cost table in `results.md` and the keep-or-drop list above. | `test_each_index_adds_write_work_and_the_batches_are_rolled_back` |
| **Diagram.** Day query at least ten times faster; latest orders without a sort step; write cost of each index recorded. | The three rows above. | |

Also tested: every migration runs twice and reverts twice without harm (`test_migrations_can_run_twice_and_be_reverted_twice_without_harm`), the committed plans say what this README says (`test_the_committed_plans_say_what_the_readme_says`), and the whole replay runs through the command-line program (`tests/e2e`).

## Quality bar

- **Layers and types:** `make lint` runs ruff (lint and format), `mypy --strict` and import-linter; CI runs it on every push, with `pip-audit` on the locked dependencies.
- **Tests:** unit (no database, domain and application at 100% coverage, gate at 95%), integration and one end-to-end replay.
- **Idempotent SQL:** `001` and `002` can run any number of times (the seed skips tables that already have rows); every migration is transactional, uses `IF [NOT] EXISTS` and has a down script; `make db` twice leaves 1,000,000 rows.
- **Operability:** structured logfmt logging to stderr, `make health` / `slow-queries-health` (exit 0, 1 or 2), SIGINT and SIGTERM stop the replay between steps (exit 130), connection and statement timeouts, connect retries with backoff and jitter, secrets only from the environment (`PGPASSWORD` has no default), a non-root `Dockerfile` with a pinned base image.

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
- **Throwaway credentials** (`lab`/`lab`) in `.env.example`, on a port that only your machine can reach. Do not reuse them anywhere.
- The seed uses `setseed`, so the data repeats; real data would not.

## Troubleshooting

- `port is already allocated`: another process uses 55431. Set `PGPORT` in `.env` and run `make down && make up`.
- `make test-integration` fails with a connection error: run `make up` and `make db` first.
- `configuration error: PGPASSWORD must be set`: copy `.env.example` to `.env` (`make up` does it for you).

## Author and license

Written by Sumit Srivastava. Released under the MIT License, see [LICENSE](LICENSE).

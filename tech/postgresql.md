# PostgreSQL

## What it is

**PostgreSQL** (often "Postgres") is a **database server**: a program that stores tables of data on disk and answers questions about them, written in a language called SQL. Many programs can connect to it at the same time over the network, and it keeps their changes consistent. It is free and open source. This repository uses major version **18**, run from the Docker image `postgres:18`.

## Why this repository uses it

The lesson is about what a real database does with a slow query, so it needs a real one with a real planner. PostgreSQL 18 is the engine the track assumes. Everything the lab teaches is observed in PostgreSQL's own output: plans, buffer counts, write-ahead-log records, statistics views.

## Where it appears

| File | What it does with PostgreSQL |
|---|---|
| `docker-compose.yml` | Starts `postgres:18` with three server settings. |
| `sql/001_schema.sql`, `002_seed.sql`, `003_queries.sql`, `reset.sql` | Create, fill, query and drop the lab's tables. |
| `sql/migrations/` and `sql/migrations/down/` | The four index changes and their undo. |
| `sql/explain/*.sql` and `*.txt` | The plans and their captured output. |
| `sql/bench/insert_10000_orders.sql` | The write-cost batch. |
| `src/slow_queries/infrastructure/` | The Python side that connects and runs these files. |

## How it works underneath

**Server and processes.** One main process, the **postmaster**, listens on a network port (5432 by default). For every client connection it starts a separate **backend process**. Other background processes write dirty data to disk, write the log, and clean up (see below).

**Objects.** A server holds several **databases**; a database holds **schemas** (folders for names; `public` by default); a schema holds **tables**, **indexes**, **sequences**, **views** (saved queries) and **functions**. A **table** has **columns** (name and type) and **rows**. Common types: `integer`/`bigint` (whole numbers), `text`, `numeric(10,2)` (exact decimals), `timestamptz` (a moment in time with time zone), `boolean`. A **sequence** hands out increasing numbers; `BIGSERIAL` is a `bigint` column fed by a sequence. A **primary key** is a column (or set) whose values are unique; PostgreSQL builds an index for it automatically.

**Pages and the heap.** Table data lives in files on disk cut into **pages** of 8 kilobytes. A page holds several rows (**tuples**). The table's own file of pages, in no particular order, is called the **heap**. Reading a row means reading its page. A page read from disk is expensive; a page already in memory is cheap. PostgreSQL keeps recently used pages in **shared buffers** (a memory cache, set here to 512 MB), and the operating system keeps its own cache as well. A plan's `Buffers: shared hit=N read=M` counts pages found in the cache (`hit`) and pages fetched from outside it (`read`). **Pages touched** (hit + read) is a stable measure of work, while milliseconds depend on the machine.

**Transactions and MVCC.** A **transaction** is a group of statements that happen all together or not at all (`BEGIN ... COMMIT`, or `ROLLBACK` to undo). PostgreSQL uses **multi-version concurrency control (MVCC)**: an `UPDATE` or `DELETE` does not overwrite a row, it writes a new version and marks the old one as dead for later transactions. Readers never block writers. The price: dead row versions pile up.

**VACUUM.** `VACUUM` removes dead row versions so the space can be reused, and updates the **visibility map**, a small bitmap that records which pages hold only rows visible to everyone. `autovacuum` is a background process that does this automatically. `VACUUM (ANALYZE)` also refreshes statistics.

**WAL (write-ahead log).** Before any change reaches the table files, PostgreSQL writes a description of it to the **write-ahead log**. After a crash the server replays the log. Every inserted row writes a WAL record for the heap *and one for every index*, which is why indexes make writes more expensive.

**The planner and statistics.** For each statement the **planner** considers several ways to get the answer and picks the one with the lowest *estimated cost*, using **statistics** that `ANALYZE` collected: the number of rows, the most common values of each column, how many distinct values there are, and how closely the order of the values matches the order of the rows on disk (all visible in the `pg_stats` view). Wrong statistics lead to bad plans. `EXPLAIN` shows the chosen plan (see the EXPLAIN note).

**TOAST.** A row must fit in a page. A big value (more than about 2 kilobytes) is moved to a separate **TOAST table** ("The Oversized-Attribute Storage Technique") and the row keeps a pointer to it; it is also compressed unless told otherwise. Queries that do not select that column never touch the TOAST table. `ALTER TABLE ... ALTER COLUMN ... SET STORAGE EXTERNAL` stores the value out of line without compression.

**Catalogs and statistics views.** PostgreSQL describes itself in tables and views you can query: `pg_stat_user_tables` (rows, last analyze), `pg_stat_user_indexes` (how often each index was used), `pg_stats` (column statistics), `pg_class` (sizes in pages), `pg_locks`, `pg_stat_activity`. `pg_relation_size(oid)` gives bytes; `pg_size_pretty(n)` formats them.

**Settings.** Server settings (`shared_buffers`, `max_parallel_workers_per_gather`...) are set at start with `postgres -c name=value`, in a config file, or per session with `SET name = value`. `SHOW name` reads one.

## Walkthrough of this repository's use

### The server and its settings

`docker-compose.yml`, lines 13 to 23:

```yaml
    command:
      - postgres
      - -c
      - max_parallel_workers_per_gather=0
      - -c
      - shared_buffers=512MB
      - -c
      - track_io_timing=on
    shm_size: 1gb
    volumes:
      - pgdata:/var/lib/postgresql
```

- `max_parallel_workers_per_gather=0`: PostgreSQL can split one big scan between several helper processes. That makes plans longer to read and timings less repeatable, so the lab switches it off, both for the whole server and again per connection (psycopg note).
- `shared_buffers=512MB`: the cache of table and index pages (8 kB each), so about 65,000 pages. The orders table is about 500 MB, more than a quarter of that cache. PostgreSQL then reads a big sequential scan through a small ring of buffers, so that one scan does not push everything else out of the cache. That is why a full scan of `orders` always reports mostly `read=` pages (`hit=2058 read=61692` in `q1_day_before.txt`), even on the second run: `read` means "not found in shared buffers", and the pages usually come from the operating system's own cache, not from the disk.
- `track_io_timing=on`: makes `EXPLAIN (ANALYZE, BUFFERS)` add `I/O Timings: shared read=...` lines, the time spent waiting for pages from outside the cache.
- The data folder is the volume `pgdata`; the image's start-up script creates the user and database from the `POSTGRES_*` variables on first start only.

### Rows, pages and TOAST in the schema

`sql/001_schema.sql`, lines 7 to 14:

```sql
CREATE TABLE IF NOT EXISTS orders (
  id          BIGSERIAL PRIMARY KEY,
  customer_id INTEGER       NOT NULL,
  status      TEXT          NOT NULL,
  created_at  TIMESTAMPTZ   NOT NULL,
  total       NUMERIC(10,2) NOT NULL,
  notes       TEXT                      -- deliberately wide: about 420 bytes a row
);
```

`orders` has about 1,000,000 rows. `notes` holds about 420 bytes per row ("customer note text - " repeated 20 times, set in the seed), so each row is about 457 bytes wide (the plans say `width=457`). With 8 kB pages that is roughly 16 rows per page and 63,000 pages in all. That wide, unused `notes` column is deliberate: it spreads the table over many pages so that scanning it is slow and an index that avoids it is a clear win.

`sql/001_schema.sql`, lines 21 to 32:

```sql
-- A small second table for the "why does a big text column cost so much" experiment.
-- Its notes column is stored out of line (TOAST), which the 420-byte notes above never are.
CREATE TABLE IF NOT EXISTS order_notes_demo (
  id          BIGSERIAL PRIMARY KEY,
  customer_id INTEGER       NOT NULL,
  status      TEXT          NOT NULL,
  created_at  TIMESTAMPTZ   NOT NULL,
  total       NUMERIC(10,2) NOT NULL,
  notes       TEXT
);
ALTER TABLE order_notes_demo ALTER COLUMN notes SET STORAGE EXTERNAL;   -- out of line, uncompressed
COMMENT ON TABLE order_notes_demo IS '20,000 orders whose 5 KB notes live in the TOAST table.';
```

`order_notes_demo` is the contrast: 20,000 rows whose `notes` is 5 kB. A value that large does not fit comfortably in a page, so PostgreSQL stores it **out of line** in a TOAST table. `ALTER TABLE ... SET STORAGE EXTERNAL` says "out of line, but do not compress". The plan evidence is in `sql/explain/q3_toast_wide.txt` (`Buffers: shared hit=207`, then after `Serialization:` another `Buffers: shared hit=10625`: reading the TOAST table to send the notes to the client) against `q3_toast_narrow.txt` (207 pages and no extra buffers).

### Statistics, skew and the planner

`sql/003_queries.sql`, lines 5 to 15:

```sql
-- Step 1: the skew landed as intended (a handful of customers with about 12,000 orders each).
SELECT customer_id, count(*) AS orders FROM orders GROUP BY customer_id ORDER BY orders DESC LIMIT 5;

-- Step 1: share of all rows held by customers 1-50 (should be about 0.60).
SELECT round(count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50)::numeric / count(*), 3) AS whale_share FROM orders;

-- Step 1: statistics are fresh (a recent timestamp, not null).
SELECT relname, last_analyze, n_live_tup FROM pg_stat_user_tables WHERE relname = 'orders';

-- Step 1: the planner has the skew too (most common values for customer_id).
SELECT n_distinct, (most_common_vals::text::int[])[1:5] AS top_customers FROM pg_stats WHERE tablename = 'orders' AND attname = 'customer_id';
```

`pg_stat_user_tables.last_analyze` shows when statistics were last collected. `pg_stats` shows what the planner knows about a column: `n_distinct` (how many different values) and `most_common_vals` (the heavy customers). The seed makes 60% of the rows belong to customers 1 to 50, and the planner's estimate for customer 7 (`rows=11873` in `q2_latest_whale_before.txt`, against 11,852 found) shows it learned the skew.

### Vacuum and the visibility map

`sql/002_seed.sql`, lines 34 to 36:

```sql
-- Statistics for the planner, and the visibility map that index-only scans need.
VACUUM (ANALYZE) orders;
VACUUM (ANALYZE) order_notes_demo;
```
`sql/migrations/003_index_listing_covering.sql`, lines 5 to 8:

```sql
CREATE INDEX IF NOT EXISTS idx_orders_listing ON orders (customer_id, created_at DESC) INCLUDE (id, status, total);
COMMIT;
-- Index-only scans need the visibility map to say the pages are all-visible (VACUUM cannot run in a transaction).
VACUUM orders;
```

After the data load, `VACUUM (ANALYZE)` does two jobs: it collects statistics and it marks the pages in the visibility map. An **index-only scan** may skip the table (heap) for a page only if the visibility map says every row on it is visible to everyone; otherwise it must visit the heap to check (counted as `Heap Fetches`). Migration `003` runs a plain `VACUUM orders` *outside* its transaction (PostgreSQL does not allow `VACUUM` inside one), so the new covering index gives `Heap Fetches: 0` in `q3_listing_after.txt`.

The replay also runs `vacuum()` after each step. The reason: the write-cost batches insert 10,000 rows and roll back, which leaves 10,000 dead row versions each time; vacuuming keeps the table tidy for the next measurement.

### Write cost and the write-ahead log

`sql/explain/results.md`, lines 21 to 27:

```markdown
| Index set | Median ms | Pages touched | WAL records | WAL MB |
|---|---:|---:|---:|---:|
| no new indexes | 59.6 | 31547 | 20357 | 5.9 |
| + idx_orders_created_at | 89.7 | 61548 | 30357 | 6.5 |
| + idx_orders_customer_created | 193.2 | 91548 | 40357 | 7.2 |
| + idx_orders_listing | 160.1 | 121561 | 50359 | 8.2 |
| idx_orders_listing only (idx_orders_customer_created dropped) | 157.6 | 91560 | 40359 | 7.5 |
```

Each added index adds about 30,000 pages touched and about 10,000 WAL records per batch of 10,000 inserted rows: one more index entry for each new row. That is the price of every read-side index, and why the lesson ends with *dropping* an index that another one makes redundant.

### Transactions in the SQL files

`sql/migrations/001_index_created_at.sql`, lines 1 to 5:

```sql
-- Step 3: the day query becomes a range on created_at; this index is what the range seeks into.
-- Safe to run twice. Undo: down/001_index_created_at.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at);
COMMIT;
```

Each migration is wrapped in `BEGIN; ... COMMIT;`, so it happens fully or not at all, and `IF NOT EXISTS` makes it safe to run twice.

## Try it yourself

(After `make up db`.)

1. `docker compose exec db psql -U lab -d lab -c "show shared_buffers" -c "show max_parallel_workers_per_gather" -c "show track_io_timing"` — prints `512MB`, `0`, `on`.
2. `docker compose exec db psql -U lab -d lab -c "select relname, relpages, reltuples::bigint from pg_class where relname = 'orders'"` — about 63,000 pages and 1,000,000 rows.
3. `docker compose exec db psql -U lab -d lab -c "select pg_size_pretty(pg_relation_size('orders')), pg_size_pretty(pg_total_relation_size('order_notes_demo'))"` — the heap size of `orders` (about 500 MB) and the total size of the demo table including its TOAST table.
4. `docker compose exec db psql -U lab -d lab -c "select n_distinct, (most_common_vals::text::int[])[1:5] from pg_stats where tablename='orders' and attname='customer_id'"` — the five most common customers (all between 1 and 50).
5. `docker compose exec db psql -U lab -d lab -c "select relname, n_dead_tup, last_autovacuum, last_vacuum from pg_stat_user_tables where relname='orders'"` — dead row versions and when vacuum last ran.

## Mistakes people make

- Assuming an index is always used (the planner may prefer a table scan, rightly or not).
- Judging a query by one timing without noticing that the cache was cold or warm.
- Forgetting `ANALYZE` after loading lots of data, so the planner works with stale statistics.
- Leaving transactions open, which stops `VACUUM` from cleaning.
- Using `SELECT *` on tables with big columns.
- Running a destructive command on the wrong database.

**How this repository avoids them.** The seed ends with `VACUUM (ANALYZE)` so the planner has statistics and the visibility map is current. Each plan is run twice (the first warms the cache) and judged mainly by pages touched, which does not depend on the machine's speed. Index changes are idempotent transactions with a down script. The rolled-back write batches are vacuumed.

## Check yourself

1. What is a page, and how big is it? *The unit in which PostgreSQL stores and reads table data: 8 kilobytes holding several rows.*
2. What does MVCC do on `UPDATE`? *It writes a new version of the row and marks the old one dead; readers keep seeing the version that fits their snapshot.*
3. What does `VACUUM` do? *Removes dead row versions so space is reused and updates the visibility map.*
4. Why do indexes make inserts slower? *Each insert must also add an entry to every index, and each of those writes a WAL record.*
5. What is TOAST? *Out-of-line storage of large values in a separate table, so ordinary rows stay small.*

## Further reading

- PostgreSQL 18 documentation: https://www.postgresql.org/docs/18/ — "Database Physical Storage" (https://www.postgresql.org/docs/18/storage.html), "Concurrency Control" (https://www.postgresql.org/docs/18/mvcc.html), "Routine Vacuuming" (https://www.postgresql.org/docs/18/routine-vacuuming.html), "Write-Ahead Logging" (https://www.postgresql.org/docs/18/wal-intro.html), "Planner statistics" (https://www.postgresql.org/docs/18/planner-stats.html).

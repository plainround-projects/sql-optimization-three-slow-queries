# SQL

## What it is

**SQL** (Structured Query Language) is the language for talking to relational databases. You describe *what* you want ("the ten newest orders of customer 7") and the database decides *how* to get it. An SQL text is made of **statements** ended by semicolons. Keywords are not case-sensitive (`select` and `SELECT` are the same); the convention is to write them in capitals.

## Why this repository uses it

The lab is SQL. The schema, the data, the queries under study, the index changes and the plans are all SQL files that you can read and run by hand. The Python code only runs them and reads the answers.

## Where it appears

| File | What it contains |
|---|---|
| `sql/001_schema.sql` | Two `CREATE TABLE` statements and comments. |
| `sql/002_seed.sql` | The data generator. |
| `sql/003_queries.sql` | The lesson's queries, slow form first. |
| `sql/reset.sql` | Drops the tables. |
| `sql/bench/insert_10000_orders.sql` | One batch of inserts for the write-cost test. |
| `sql/migrations/001` to `004` | The index changes. |
| `sql/migrations/down/001` to `004` | Their undo scripts. |
| `sql/explain/*.sql` | The `EXPLAIN` statements. |

## How it works underneath

**Data definition (DDL):** statements that create or change structure.

- `CREATE TABLE name (column type constraints, ...)`: a new table. Constraints: `PRIMARY KEY` (unique, not null, indexed), `NOT NULL`.
- `CREATE INDEX name ON table (columns)`; `DROP INDEX name`; `DROP TABLE name`; `ALTER TABLE ...`.
- `COMMENT ON TABLE t IS 'text'` attaches a description stored in the database.
- `IF NOT EXISTS` / `IF EXISTS` make a statement do nothing instead of failing when the object already exists / is already gone. This makes scripts **idempotent**: safe to run twice.

**Queries and data changes (DML):**

- `SELECT columns FROM table WHERE condition GROUP BY columns ORDER BY column [DESC] LIMIT n`.
  - `WHERE` keeps rows for which the condition is true. `AND`, `OR`, `NOT`, `BETWEEN a AND b`, `=`, `<`, `>=`.
  - `GROUP BY` makes groups; aggregate functions summarise each group: `count(*)`, `max(x)`, `sum(x)`.
  - `ORDER BY` sorts (`DESC` is descending). `LIMIT n` keeps the first n rows.
  - `count(*) FILTER (WHERE condition)` counts only the rows meeting the condition.
  - `SELECT *` returns every column.
- `INSERT INTO table (columns) SELECT ... FROM generate_series(1, 1000000)`: inserts the rows a query produces. `generate_series(a, b)` produces the numbers a to b.
- `UPDATE`, `DELETE` change or remove rows.

**Expressions.** `x::int` converts the type (a **cast**). `CASE WHEN condition THEN a ELSE b END` chooses. `(ARRAY['a','b'])[2]` picks the second element of an array (counting starts at 1). `timestamp '2026-01-01' + n * interval '1 day'` adds a span of time. Text literals use single quotes; `''` inside means a quote. Double quotes name identifiers.

**Functions used here.** `random()` returns a decimal between 0 and 1; `floor(x)`; `round(x, 2)`; `repeat('ab', 3)` gives `ababab`; `md5(text)`; `string_agg(x, '')` joins text values; `date(timestamp)` extracts the date; `setseed(0.42)` makes `random()` repeatable.

**Transactions.** `BEGIN;` starts a group of statements, `COMMIT;` saves them all, `ROLLBACK;` throws them away.

**Maintenance and inspection statements.** `VACUUM`, `ANALYZE`, `EXPLAIN`, `SET timezone = 'UTC'` (change a session setting), `SHOW`.

**Comments.** `-- to end of line`. A statement ends at `;`.

**NULL** means "no value / unknown". `x = NULL` is never true; use `x IS NULL`. `NOT EXISTS (SELECT 1 FROM t)` is true when the table has no rows.

## Walkthrough of this repository's use

### `001_schema.sql`: structure

`sql/001_schema.sql`, lines 1 to 34:

```sql
-- 001_schema.sql: DDL for the "Three slow queries" lab (PostgreSQL 18). Safe to run twice: every statement is
-- IF NOT EXISTS or idempotent, and the whole file is one transaction.
-- Only the primary key is indexed. Every other index in this project is added by a migration, one at a time,
-- after reading the plan that justifies it.
BEGIN;

CREATE TABLE IF NOT EXISTS orders (
  id          BIGSERIAL PRIMARY KEY,
  customer_id INTEGER       NOT NULL,
  status      TEXT          NOT NULL,
  created_at  TIMESTAMPTZ   NOT NULL,
  total       NUMERIC(10,2) NOT NULL,
  notes       TEXT                      -- deliberately wide: about 420 bytes a row
);

COMMENT ON TABLE  orders             IS 'One million skewed orders: 60% belong to customers 1-50.';
COMMENT ON COLUMN orders.customer_id IS 'Customers 1-50 are the heavy ones; 51-50000 get a handful each.';
COMMENT ON COLUMN orders.created_at  IS 'Spans exactly one year (2026) so the day query has data to find.';
COMMENT ON COLUMN orders.notes       IS 'Wide free text the listing never shows; makes every heap page hold fewer rows.';

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

COMMIT;
```

- Lines 1 to 4: comments. The file is one transaction (`BEGIN;` line 5 to `COMMIT;` line 34): either both tables are created or neither.
- `CREATE TABLE IF NOT EXISTS orders (...)`: creates the table unless it exists. Columns: `id BIGSERIAL PRIMARY KEY` (a `bigint` filled from a sequence, the unique key), `customer_id INTEGER NOT NULL`, `status TEXT NOT NULL`, `created_at TIMESTAMPTZ NOT NULL` (a moment in time), `total NUMERIC(10,2) NOT NULL` (an exact decimal with 10 digits, 2 after the point), and `notes TEXT` (may be empty). The trailing `--` comment on `notes` explains the width.
- Lines 16 to 19: `COMMENT ON TABLE/COLUMN ... IS '...'` store descriptions in the database (you can read them with `\d+ orders`).
- Lines 23 to 30: the second table has the same shape. Line 31: `ALTER TABLE order_notes_demo ALTER COLUMN notes SET STORAGE EXTERNAL;` changes how the column's large values are stored (PostgreSQL note). Line 32 is its comment.

### `002_seed.sql`: data

`sql/002_seed.sql`, lines 1 to 9:

```sql
-- 002_seed.sql: DML. One million orders with real skew, then fresh statistics.
-- Safe to run twice: a table that already has rows is left alone (use `make reset` to start from nothing).
-- setseed makes the "random" data identical on every run, so the notes and plans repeat.
SELECT setseed(0.42);
SET timezone = 'UTC';

SELECT NOT EXISTS (SELECT 1 FROM orders) AS orders_empty,
       NOT EXISTS (SELECT 1 FROM order_notes_demo) AS demo_empty \gset

```

- `SELECT setseed(0.42);` fixes the starting point of `random()`, so every run produces the same "random" data. `SET timezone = 'UTC';` makes timestamp literals mean UTC.
- Lines 7 and 8 compute two true/false values in one query: `NOT EXISTS (SELECT 1 FROM orders) AS orders_empty` is true when the table has no rows; the same for `demo_empty`. The final `\gset` is not SQL: it is a `psql` command (psql note) that stores the result columns in psql variables named `orders_empty` and `demo_empty`.

`sql/002_seed.sql`, lines 10 to 22:

```sql
\if :orders_empty
BEGIN;
INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT
  CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int          -- 60% of rows go to 50 customers
       ELSE 51 + floor(random() * 49950)::int END,
  (ARRAY['pending','paid','shipped','failed'])[1 + floor(random() * 4)::int],
  timestamp '2026-01-01' + (random() * 365) * interval '1 day',
  round((random() * 500 + 5)::numeric, 2),
  repeat('customer note text - ', 20)                                  -- a deliberately wide notes column
FROM generate_series(1, 1000000);
COMMIT;
\endif
```

- `\if :orders_empty ... \endif` (also psql commands) run the block only if the variable is true. So a second `make db` does not load a second million rows. `BEGIN;` and `COMMIT;` wrap the insert.
- `INSERT INTO orders (customer_id, status, created_at, total, notes) SELECT ... FROM generate_series(1, 1000000);` runs the `SELECT` once for each number from 1 to 1,000,000 and inserts every produced row.
- `CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int ELSE 51 + floor(random() * 49950)::int END`: with probability 60% pick a customer from 1 to 50 (`random() * 50` is between 0 and 50, `floor` rounds down, `::int` makes it an integer, plus 1), otherwise from 51 to 50,000. That is the skew.
- `(ARRAY['pending','paid','shipped','failed'])[1 + floor(random() * 4)::int]` picks one of four statuses at random.
- `timestamp '2026-01-01' + (random() * 365) * interval '1 day'` is a random moment in 2026 (a random number of days from 0 to 365 added to January 1).
- `round((random() * 500 + 5)::numeric, 2)` is a price between 5 and 505 with 2 decimals.
- `repeat('customer note text - ', 20)` repeats the phrase 20 times: about 420 characters.

`sql/002_seed.sql`, lines 24 to 36:

```sql
-- 20,000 rows with a 5 KB incompressible-ish note (160 distinct md5 strings) for the TOAST demo.
\if :demo_empty
BEGIN;
INSERT INTO order_notes_demo (customer_id, status, created_at, total, notes)
SELECT 7, 'paid', timestamp '2026-01-01' + (series.n * interval '15 minutes'), 10.00,
       (SELECT string_agg(md5(series.n::text || part::text), '') FROM generate_series(1, 160) AS part)
FROM generate_series(1, 20000) AS series(n);
COMMIT;
\endif

-- Statistics for the planner, and the visibility map that index-only scans need.
VACUUM (ANALYZE) orders;
VACUUM (ANALYZE) order_notes_demo;
```

- The demo table gets 20,000 rows. `timestamp '2026-01-01' + (series.n * interval '15 minutes')` gives each row a time 15 minutes after the previous one. The notes expression is a **scalar subquery**: `(SELECT string_agg(md5(series.n::text || part::text), '') FROM generate_series(1, 160) AS part)` builds, for every row, the join (`string_agg` with an empty separator) of 160 different MD5 hashes (each 32 characters), which makes a 5,120-character note that does not compress well; `||` joins text.
- `FROM generate_series(1, 20000) AS series(n)` names the table alias `series` and its column `n`.
- Lines 35 and 36: `VACUUM (ANALYZE) orders;` and the same for the demo table.

### `003_queries.sql`: the lesson's queries

`sql/003_queries.sql`, lines 1 to 47:

```sql
-- 003_queries.sql: every query the lesson runs, in its slow form first.
-- `make db` runs this file after the seed; plans for the same queries live in explain/.
SET timezone = 'UTC';

-- Step 1: the skew landed as intended (a handful of customers with about 12,000 orders each).
SELECT customer_id, count(*) AS orders FROM orders GROUP BY customer_id ORDER BY orders DESC LIMIT 5;

-- Step 1: share of all rows held by customers 1-50 (should be about 0.60).
SELECT round(count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50)::numeric / count(*), 3) AS whale_share FROM orders;

-- Step 1: statistics are fresh (a recent timestamp, not null).
SELECT relname, last_analyze, n_live_tup FROM pg_stat_user_tables WHERE relname = 'orders';

-- Step 1: the planner has the skew too (most common values for customer_id).
SELECT n_distinct, (most_common_vals::text::int[])[1:5] AS top_customers FROM pg_stats WHERE tablename = 'orders' AND attname = 'customer_id';

-- Query 1, slow form: a function on the column hides it from any index on created_at.
SELECT count(*) FROM orders WHERE date(created_at) = '2026-03-14';

-- Query 1, fixed form: a half-open range on the raw column that an index can seek into.
SELECT count(*) FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15';

-- Query 2: one heavy customer's ten newest orders (no index yet: scan, then sort).
SELECT id, created_at, status, total FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10;

-- Query 2: the same query for a customer with only a handful of orders.
SELECT id, created_at, status, total FROM orders WHERE customer_id = 31337 ORDER BY created_at DESC LIMIT 10;

-- Query 3, slow form: SELECT * fetches the wide notes column to show five columns (output discarded).
\o /dev/null
SELECT * FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC LIMIT 5;
\o

-- Query 3, fixed form: only the five columns the listing renders.
SELECT id, customer_id, status, created_at, total FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC LIMIT 5;

-- Step 6: the write cost experiment, one batch of 10,000 orders (run inside a transaction you roll back).
-- `make run` does it for you, once per index configuration.
BEGIN;
INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int ELSE 51 + floor(random() * 49950)::int END,
       'pending', timestamp '2026-01-01' + (random() * 365) * interval '1 day', 10.00, repeat('customer note text - ', 20)
FROM generate_series(1, 10000);
ROLLBACK;

-- Index inspection: which indexes exist, how big, how often scanned.
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size, idx_scan FROM pg_stat_user_indexes WHERE relname = 'orders' ORDER BY indexrelname;
```

- Line 3: `SET timezone = 'UTC';`.
- Line 6: group by customer, count, `ORDER BY orders DESC LIMIT 5`: the five biggest customers.
- Line 9: `count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50)::numeric / count(*)` is the share of rows held by customers 1 to 50; `round(..., 3)` gives about 0.600.
- Lines 12 and 15: the statistics views (PostgreSQL note). `(most_common_vals::text::int[])[1:5]` converts the stored list to text and then to an integer array and takes elements 1 to 5.
- Lines 18 and 21: the two forms of query 1.
- Lines 24 and 27: query 2 for a heavy and a light customer.
- Lines 30 to 32: `\o /dev/null` (psql: send output to nowhere) hides the wide rows of the `SELECT *`; the bare `\o` restores normal output. Line 35: the narrow listing.
- Lines 39 to 44: the write-cost experiment in plain SQL: `BEGIN;` insert 10,000 rows, `ROLLBACK;` throws them away.
- Line 47: the sizes and use counts of the indexes: `pg_size_pretty(pg_relation_size(indexrelid))` formats the size in bytes; `idx_scan` counts how often each index was used.

### `reset.sql`, `bench/` and the migrations

`sql/reset.sql`, lines 1 to 5:

```sql
-- reset.sql: drop everything the lab created, so 001 to 002 rebuild it from nothing. `make reset` runs this.
BEGIN;
DROP TABLE IF EXISTS order_notes_demo;
DROP TABLE IF EXISTS orders CASCADE;
COMMIT;
```
`sql/bench/insert_10000_orders.sql`, lines 1 to 7:

```sql
-- One batch of 10,000 inserts, shaped like the seed (60% to the heavy customers, random times). The write-cost
-- measurement runs it under EXPLAIN (ANALYZE, BUFFERS, WAL) and rolls it back, once per index set.
INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int ELSE 51 + floor(random() * 49950)::int END,
       'pending', timestamp '2026-01-01' + (random() * 365) * interval '1 day', 10.00,
       repeat('customer note text - ', 20)
FROM generate_series(1, 10000);
```
`sql/migrations/down/004_drop_superseded_index.down.sql`, lines 1 to 4:

```sql
-- Undo migration 004: bring the narrow index back. Safe to run twice.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_customer_created ON orders (customer_id, created_at DESC);
COMMIT;
```

`reset.sql` drops both tables in one transaction (`CASCADE` also drops things that depend on `orders`). The bench file is one `INSERT ... SELECT` of 10,000 rows shaped like the seed; the Python code puts `EXPLAIN (ANALYZE, BUFFERS, WAL)` in front of it and rolls back. The migration files are covered in the PostgreSQL-indexes note; the down scripts mirror them (`DROP INDEX IF EXISTS` for 001 to 003, and `CREATE INDEX IF NOT EXISTS` to restore the narrow index for 004), each in `BEGIN; ... COMMIT;`.

### The remaining SQL files, line by line

Every file below is a plain SQL script. A line that starts with two hyphens (`--`) is a **comment**: text for the reader, ignored by PostgreSQL. A statement ends at a semicolon. `EXPLAIN` asks PostgreSQL to show how it would run a query instead of returning the rows; with the option `ANALYZE` it really runs the query and adds the measured times; `BUFFERS` adds how many 8 kilobyte pages were touched; `SERIALIZE` (PostgreSQL 17 and later) also measures the work of turning the rows into the text sent to the client, which matters when a column holds a large value. `SET timezone = 'UTC';` makes the session read and print timestamps in UTC, so that the date literals below mean the same thing on every machine.

#### The "down" migrations

Each migration has a script that undoes it. `BEGIN;` starts a transaction (a group of statements that either all take effect or none does) and `COMMIT;` ends it and makes it permanent. `DROP INDEX IF EXISTS name;` removes an index, and the words `IF EXISTS` make it a quiet no-op when the index is already gone, which is why each file says it is safe to run twice.

`sql/migrations/down/001_index_created_at.down.sql`, lines 1 to 4:

```sql
-- Undo migration 001. Safe to run twice.
BEGIN;
DROP INDEX IF EXISTS idx_orders_created_at;
COMMIT;
```

Undoes migration 001 by removing `idx_orders_created_at`, the index on the creation time.

`sql/migrations/down/002_index_customer_created.down.sql`, lines 1 to 4:

```sql
-- Undo migration 002. Safe to run twice.
BEGIN;
DROP INDEX IF EXISTS idx_orders_customer_created;
COMMIT;
```

Undoes migration 002 by removing `idx_orders_customer_created`, the index on the customer and creation time together.

`sql/migrations/down/003_index_listing_covering.down.sql`, lines 1 to 4:

```sql
-- Undo migration 003. Safe to run twice.
BEGIN;
DROP INDEX IF EXISTS idx_orders_listing;
COMMIT;
```

Undoes migration 003 by removing `idx_orders_listing`, the covering index (an index that also stores the other columns a query needs, so the table itself need not be read).

#### The explain scripts

Each of these files is run by the replay; the plan it prints is saved as a text file with the same name and quoted by the tests and the results notes.

`sql/explain/q1_day_after.sql`, lines 1 to 4:

```sql
-- Query 1 after: a half-open range on the raw column, served by idx_orders_created_at (migration 001).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15';
```

Query 1 after migration 001. The condition is a half-open range on the raw column: `created_at >= '2026-03-14' AND created_at < '2026-03-15'` includes midnight of the 14th and excludes midnight of the 15th, so every moment of that day is matched exactly once, and, because the column is not wrapped in a function, the index on `created_at` can be used.

`sql/explain/q2_latest_whale_before.sql`, lines 1 to 4:

```sql
-- Query 2 before, a heavy customer (about 12,000 orders): scan every row, then top-N sort.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10;
```

Query 2 before the index, for customer 7, who has about 12,000 orders. `ORDER BY created_at DESC LIMIT 10` asks for the newest ten. With no index on the customer, PostgreSQL must read every row of the table, keep the rows of customer 7 and sort them, keeping only the top ten (a "top-N sort").

`sql/explain/q2_latest_whale_after.sql`, lines 1 to 4:

```sql
-- Query 2 after, the same heavy customer: ten index entries, no Sort node (migration 002).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10;
```

The same query after migration 002. The index on `(customer_id, created_at)` holds each customer's orders in time order, so PostgreSQL can walk it backwards for ten entries and stop: no sort node is needed.

`sql/explain/q2_latest_small_before.sql`, lines 1 to 4:

```sql
-- Query 2 before, a customer with 7 orders: still a full scan, because nothing finds the customer.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 31337 ORDER BY created_at DESC LIMIT 10;
```

The same question for customer 31337, who has only 7 orders. Before the index the table is still read in full, because nothing can find a customer's rows without scanning.

`sql/explain/q2_latest_small_after.sql`, lines 1 to 4:

```sql
-- Query 2 after, the same small customer: seven entries, already in order (migration 002).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 31337 ORDER BY created_at DESC LIMIT 10;
```

After migration 002 the seven entries are read in order from the index. `LIMIT 10` asks for more rows than exist, so all seven come back.

`sql/explain/q3_listing_before.sql`, lines 1 to 5:

```sql
-- Query 3 before: SELECT * for a listing that shows five columns; with idx_orders_customer_created the
-- rows are found fast, but every heap page is visited and the wide notes column is sent to the client.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT * FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC;
```

Query 3 before the covering index: a listing page for customer 7 for the month of March 2026. The two comment lines explain it: `SELECT *` returns every column, including the wide `notes` column, so even with the index on customer and time every row's table page is visited and the notes are sent to the client. The date range is again half-open, from the first of March up to but not including the first of April.

`sql/explain/q3_listing_narrow.sql`, lines 1 to 5:

```sql
-- Query 3, the five columns named but no covering index yet: the same heap pages are still visited;
-- the notes column is inline here, so naming columns only shrinks what is sent to the client.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT id, customer_id, status, created_at, total FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC;
```

The same listing with the five columns the page displays named instead of `*`. Without a covering index the same table pages are still visited; the comment says the notes column is stored inline here, so naming columns only shrinks what is sent to the client.

`sql/explain/q3_listing_after.sql`, lines 1 to 4:

```sql
-- Query 3 after: five columns and the covering index idx_orders_listing (migration 003), no heap visits.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT id, customer_id, status, created_at, total FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC;
```

The five-column listing after migration 003. The covering index `idx_orders_listing` contains all five columns, so the plan can be an index-only scan with no visits to the table.

`sql/explain/q3_toast_narrow.sql`, lines 1 to 4:

```sql
-- The same rows without the note: the TOAST table is never read.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT id, customer_id, status, created_at, total FROM order_notes_demo WHERE customer_id = 7 AND created_at < '2026-02-01';
```

A demonstration on the table `order_notes_demo`, which has a very large `note` column. PostgreSQL stores values that large outside the main table, in a side table called the TOAST table. Selecting only the small columns means the side table is never read; the comment says so. The condition `created_at < '2026-02-01'` selects the old rows of customer 7.

## Try it yourself

(After `make up db`; `P="docker compose exec -T db psql -U lab -d lab"`.)

1. `$P -c "select customer_id, count(*) from orders group by 1 order by 2 desc limit 3"` — three customers with about 12,000 orders each.
2. `$P -c "select status, count(*) from orders group by status order by 1"` — four statuses, about 250,000 each.
3. `$P -c "select (array['a','b','c'])[2], 7::text || 'x', floor(2.9), round(2.456, 2)"` — prints `b`, `7x`, `2`, `2.46`.
4. `make db` a second time — finishes quickly and `$P -c "select count(*) from orders"` still says 1,000,000: the guarded seed did nothing.
5. `make reset db` — drops and rebuilds everything (about 30 seconds).

## Mistakes people make

- `SELECT *` in application queries.
- Comparing with `= NULL`.
- Forgetting `WHERE` on `UPDATE` and `DELETE`.
- Wrapping an indexed column in a function in `WHERE`.
- Assuming rows come back in a fixed order without `ORDER BY`.
- Running a script twice and getting "already exists" errors (use `IF NOT EXISTS`).
- Time zone surprises with `timestamp` versus `timestamptz`.

**How this repository avoids them.** No `SELECT *` in the code paths under study (except to show its cost). Every DDL has `IF [NOT] EXISTS`. The seed refuses to double-load. Time zone is fixed with `SET timezone`. Ordering is always explicit where order matters.

## Check yourself

1. What do `WHERE` and `GROUP BY` each do? *`WHERE` filters rows; `GROUP BY` forms groups for aggregate functions.*
2. What does `IF NOT EXISTS` give a script? *Safe repetition: nothing happens, and no error, if the object exists.*
3. What does `x::int` do? *Converts the value `x` to the type integer.*
4. What happens to the statements between `BEGIN` and `ROLLBACK`? *Their effects are discarded.*
5. Why is `col = NULL` never true? *NULL means unknown, and comparing with unknown yields unknown; use `IS NULL`.*

## Further reading

- PostgreSQL 18, "SQL Commands": https://www.postgresql.org/docs/18/sql-commands.html and "The SQL Language": https://www.postgresql.org/docs/18/sql.html
- "Functions and Operators": https://www.postgresql.org/docs/18/functions.html

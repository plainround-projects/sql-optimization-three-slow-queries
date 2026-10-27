# PostgreSQL indexes

## What it is

An **index** is a second structure kept beside a table that lets the database find rows without reading the whole table, like the index at the back of a book. Without one, finding the rows with `customer_id = 7` means reading every page of the table (a **sequential scan**). With one, the database looks up `7` in a small sorted structure and goes straight to the matching rows.

## Why this repository uses it

Indexes are the lesson. Each of the three slow queries is fixed by one index (or by rewriting the query so that an index can be used), and the last step measures what each index costs. The migrations add them one at a time, after reading the plan that justifies each.

## Where it appears

| File | Index |
|---|---|
| `sql/001_schema.sql` | Only the primary key: `id BIGSERIAL PRIMARY KEY` creates `orders_pkey`. |
| `sql/migrations/001_index_created_at.sql` | `idx_orders_created_at` on `(created_at)`. |
| `sql/migrations/002_index_customer_created.sql` | `idx_orders_customer_created` on `(customer_id, created_at DESC)`. |
| `sql/migrations/003_index_listing_covering.sql` | `idx_orders_listing` on `(customer_id, created_at DESC) INCLUDE (id, status, total)`. |
| `sql/migrations/004_drop_superseded_index.sql` | Drops the narrow one. |
| `sql/explain/*.txt` | The plans that show each index at work. |

## How it works underneath

**B-tree.** The default index type is a **B-tree**: a balanced tree of 8 kB pages. The top page lists ranges of key values and points to pages below; the bottom pages (**leaf pages**) hold the keys in sorted order, each with a pointer (the row's physical address) to the row in the table. Finding one key takes only a handful of page reads, even for a million rows, because the tree is shallow. Because the leaves are sorted, a B-tree also answers range questions (`created_at >= x AND created_at < y`) by finding the start and reading forward, and it can return rows already in sorted order (so no separate sort step is needed).

**Multi-column indexes.** `(customer_id, created_at DESC)` sorts by `customer_id` first, and rows with the same customer by `created_at` newest first. All the rows of one customer therefore sit together, newest first. The index helps queries that fix the first column (equality) and then use the next (a range or an order). It does *not* help a query that only mentions `created_at`. The column order matters: equality columns first, then the range or sort column.

**Direction.** `DESC` stores that column in descending order, so "newest first" can be read from the start.

**Covering index (`INCLUDE`).** `CREATE INDEX ... (a, b) INCLUDE (c, d)` also stores `c` and `d` in the leaf pages, though they are not part of the sort key. A query that needs only `a, b, c, d` can be answered from the index alone: an **index-only scan**, which never visits the table. The catch: the index entry does not say whether the row is *visible* to the current transaction, so PostgreSQL consults the **visibility map**; if the page is marked all-visible it trusts the index, otherwise it visits the table page (a *heap fetch*). `VACUUM` keeps the visibility map current.

**Scan types you will see in plans.**

- `Seq Scan`: read the whole table.
- `Index Scan`: walk the index and fetch each matching row from the table in index order.
- `Index Only Scan`: answer from the index alone.
- `Bitmap Index Scan` + `Bitmap Heap Scan`: collect all matching row addresses from the index into a bitmap, sort them by page, then read each table page once. Used when many rows match.

**Why a function on the column blocks the index.** An index on `created_at` is sorted by `created_at`, not by `date(created_at)`. The condition `date(created_at) = '2026-03-14'` forces the database to compute the function for every row. Rewrite it as a range on the bare column: `created_at >= '2026-03-14' AND created_at < '2026-03-15'`. Conditions that an index can use are called **sargable** (search-argument-able).

**Costs.** An index takes disk space and slows every `INSERT`, `UPDATE` and `DELETE` (each change must update every index, and writes WAL for it). Add an index when a read is worth that cost; drop one that another index makes redundant: `(customer_id, created_at) INCLUDE (...)` has the same leading columns as `(customer_id, created_at)`, so it serves the same lookups.

**`CREATE INDEX IF NOT EXISTS`** makes creation safe to repeat. A plain `CREATE INDEX` blocks writes to the table while it builds; `CREATE INDEX CONCURRENTLY` does not (but cannot run inside a transaction and takes longer).

## Walkthrough of this repository's use

### Query 1: the day query and `idx_orders_created_at`

`sql/003_queries.sql`, lines 17 to 21:

```sql
-- Query 1, slow form: a function on the column hides it from any index on created_at.
SELECT count(*) FROM orders WHERE date(created_at) = '2026-03-14';

-- Query 1, fixed form: a half-open range on the raw column that an index can seek into.
SELECT count(*) FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15';
```
`sql/migrations/001_index_created_at.sql`, lines 1 to 5:

```sql
-- Step 3: the day query becomes a range on created_at; this index is what the range seeks into.
-- Safe to run twice. Undo: down/001_index_created_at.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at);
COMMIT;
```

The slow form wraps the column in `date(...)`. The captured plan, `q1_day_before.txt`, is a `Seq Scan on orders` with `Rows Removed by Filter: 997252`: it read all 1,000,000 rows, kept 2,748 and threw away the rest. The fixed form uses a half-open range (`>=` the start, `<` the next day). With `idx_orders_created_at` the plan becomes a bitmap scan (`q1_day_after.txt`, 2,713 pages touched against 63,750). Why bitmap and not a plain index scan: 2,748 rows are scattered over many pages, so collecting addresses first and then reading each page once is cheaper.

### Query 2: the latest ten orders and the column order

`sql/003_queries.sql`, lines 23 to 27:

```sql
-- Query 2: one heavy customer's ten newest orders (no index yet: scan, then sort).
SELECT id, created_at, status, total FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10;

-- Query 2: the same query for a customer with only a handful of orders.
SELECT id, created_at, status, total FROM orders WHERE customer_id = 31337 ORDER BY created_at DESC LIMIT 10;
```
`sql/migrations/002_index_customer_created.sql`, lines 1 to 6:

```sql
-- Step 4: equality column first, then the sort column in the direction the query wants.
-- One customer's rows sit together, newest first, so LIMIT 10 reads ten entries and stops.
-- Safe to run twice. Undo: down/002_index_customer_created.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_customer_created ON orders (customer_id, created_at DESC);
COMMIT;
```

`WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10`: an equality, a sort and a limit. Before the index, the plan (`q2_latest_whale_before.txt`) is `Seq Scan` plus `Sort Method: top-N heapsort`, 63,750 pages, 543 ms. After it (`q2_latest_whale_after.txt`): `Index Scan using idx_orders_customer_created` with no `Sort` node and `Buffers: shared hit=13`, 0.03 ms. The index is `(customer_id, created_at DESC)`: equality column first, then the sort column in the direction asked, so the first ten entries of customer 7 are the ten newest orders and `LIMIT 10` stops after reading them. The same plan works for customer 31337 who has only a handful of orders (10 pages).

### Query 3: the listing and the covering index

`sql/003_queries.sql`, lines 29 to 35:

```sql
-- Query 3, slow form: SELECT * fetches the wide notes column to show five columns (output discarded).
\o /dev/null
SELECT * FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC LIMIT 5;
\o

-- Query 3, fixed form: only the five columns the listing renders.
SELECT id, customer_id, status, created_at, total FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC LIMIT 5;
```
`sql/migrations/003_index_listing_covering.sql`, lines 1 to 8:

```sql
-- Step 5: a covering index for the five-column listing. INCLUDE stores the other listed
-- columns in the leaf pages, so the heap (and the wide notes column) is never visited.
-- Safe to run twice. Undo: down/003_index_listing_covering.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_listing ON orders (customer_id, created_at DESC) INCLUDE (id, status, total);
COMMIT;
-- Index-only scans need the visibility map to say the pages are all-visible (VACUUM cannot run in a transaction).
VACUUM orders;
```

`SELECT *` returns the 420-byte `notes` column that the listing never shows. Using only five columns fixes the output width but, as `q3_listing_narrow.txt` shows (still 1,009 pages), not the number of pages read, because the rows still have to be fetched from the table. The covering index stores `id, status, total` in its leaf pages next to `(customer_id, created_at)`, so the five columns the listing needs (`id, customer_id, status, created_at, total`) are all in the index. The plan `q3_listing_after.txt` is `Index Only Scan using idx_orders_listing` with `Heap Fetches: 0` and 506 pages. The `VACUUM orders` at the end of the migration (outside the transaction) refreshes the visibility map that makes `Heap Fetches: 0` possible.

### Step 6: cost, and dropping the redundant one

`sql/migrations/004_drop_superseded_index.sql`, lines 1 to 6:

```sql
-- Step 6, contract: idx_orders_listing has the same leading columns as idx_orders_customer_created, so it
-- serves query 2 as well. Keeping both pays the write cost twice for no read benefit: drop the narrow one.
-- Safe to run twice. Undo: down/004_drop_superseded_index.down.sql.
BEGIN;
DROP INDEX IF EXISTS idx_orders_customer_created;
COMMIT;
```
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

Every index adds about 30,000 pages touched and 10,000 WAL records per 10,000 inserts. After the covering index exists, `idx_orders_customer_created` is redundant: both start with `(customer_id, created_at DESC)`. Migration 004 drops it. The last row of the table shows 91,560 pages and 40,359 WAL records, about one index cheaper than the row above. `sql/migrations/down/004_drop_superseded_index.down.sql` brings it back.

## Try it yourself

(After `make up db`.)

1. `make run` — replays the lesson and rewrites `sql/explain/`; afterwards `git diff --stat sql/explain` shows which plans changed (their timings will, their shapes will not).
2. `docker compose exec db psql -U lab -d lab -c "\d orders"` — lists the columns and the indexes that exist now (just `orders_pkey` after `make db`).
3. `docker compose exec -T db psql -U lab -d lab < sql/migrations/001_index_created_at.sql`, then `docker compose exec db psql -U lab -d lab -c "\di+ idx_orders_created_at"` — shows the new index and its size (about 22 MB).
4. `docker compose exec db psql -U lab -d lab -c "explain select count(*) from orders where created_at >= '2026-03-14' and created_at < '2026-03-15'"` — plain `EXPLAIN` (no execution) now chooses an index-based plan.
5. Undo with `docker compose exec -T db psql -U lab -d lab < sql/migrations/down/001_index_created_at.down.sql`.

## Mistakes people make

- Indexing every column "just in case".
- Putting a range column before an equality column in a multi-column index.
- Wrapping the indexed column in a function in the `WHERE` clause.
- Forgetting that an index must be maintained on every write.
- Expecting an index-only scan on a table that was never vacuumed.
- Keeping two indexes where one covers both.

**How this repository avoids them.** Indexes are added one at a time, each after a plan justifies it. The column order puts equality before sort. The query is rewritten to be sargable before the index is blamed. The write cost of each index is measured, and a redundant one is dropped with a down script that can bring it back.

## Check yourself

1. Why is a B-tree lookup fast even for a million rows? *The tree is shallow, so only a few pages are read to find one key.*
2. Why does `date(created_at) = '2026-03-14'` not use an index on `created_at`? *The index is sorted by the raw column, not by the function result; the database would have to compute the function for every row.*
3. In `(customer_id, created_at DESC)`, which queries are served? *Those that fix `customer_id` and then filter or order by `created_at`, newest first.*
4. What does `INCLUDE (id, status, total)` add? *The extra columns are stored in the leaf pages so a query needing only those columns can be answered without visiting the table.*
5. What does `Heap Fetches: 0` mean in an index-only scan? *Every page was marked all-visible, so no table page had to be visited.*

## Further reading

- PostgreSQL 18, "Indexes": https://www.postgresql.org/docs/18/indexes.html — "Index Types" (B-tree), "Multicolumn Indexes", "Indexes and ORDER BY", "Index-Only Scans and Covering Indexes" (https://www.postgresql.org/docs/18/indexes-index-only-scans.html).
- `CREATE INDEX`: https://www.postgresql.org/docs/18/sql-createindex.html

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
-- scripts/run_lesson.py runs it for you, once per index configuration.
BEGIN;
INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int ELSE 51 + floor(random() * 49950)::int END,
       'pending', timestamp '2026-01-01' + (random() * 365) * interval '1 day', 10.00, repeat('customer note text - ', 20)
FROM generate_series(1, 10000);
ROLLBACK;

-- Index inspection: which indexes exist, how big, how often scanned.
SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size, idx_scan FROM pg_stat_user_indexes WHERE relname = 'orders' ORDER BY indexrelname;

-- Query 2 before, a heavy customer (about 12,000 orders): scan every row, then top-N sort.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10;

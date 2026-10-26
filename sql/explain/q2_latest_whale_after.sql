-- Query 2 after, the same heavy customer: ten index entries, no Sort node (migration 002).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 7 ORDER BY created_at DESC LIMIT 10;

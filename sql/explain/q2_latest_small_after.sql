-- Query 2 after, the same small customer: seven entries, already in order (migration 002).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 31337 ORDER BY created_at DESC LIMIT 10;

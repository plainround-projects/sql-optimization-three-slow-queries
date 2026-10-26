-- Query 1 before: date(created_at) wraps the column, so no index on created_at can be used.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE date(created_at) = '2026-03-14';

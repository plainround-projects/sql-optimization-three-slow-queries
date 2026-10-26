-- Query 1 after: a half-open range on the raw column, served by idx_orders_created_at (migration 001).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15';

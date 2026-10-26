-- Query 3 after: five columns and the covering index idx_orders_listing (migration 003), no heap visits.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT id, customer_id, status, created_at, total FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC;

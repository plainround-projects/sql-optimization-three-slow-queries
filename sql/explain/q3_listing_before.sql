-- Query 3 before: SELECT * for a listing that shows five columns; with idx_orders_customer_created the
-- rows are found fast, but every heap page is visited and the wide notes column is sent to the client.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT * FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC;

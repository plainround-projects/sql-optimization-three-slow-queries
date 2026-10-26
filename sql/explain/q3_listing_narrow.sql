-- Query 3, the five columns named but no covering index yet: the same heap pages are still visited;
-- the notes column is inline here, so naming columns only shrinks what is sent to the client.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT id, customer_id, status, created_at, total FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' ORDER BY created_at DESC;

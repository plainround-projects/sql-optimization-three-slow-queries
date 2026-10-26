-- The same rows without the note: the TOAST table is never read.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT id, customer_id, status, created_at, total FROM order_notes_demo WHERE customer_id = 7 AND created_at < '2026-02-01';

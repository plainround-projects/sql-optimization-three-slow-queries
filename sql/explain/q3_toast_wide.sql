-- Why a big text column costs: SELECT * on 20,000 rows whose 5 KB note is stored out of line (TOAST).
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS, SERIALIZE)
SELECT * FROM order_notes_demo WHERE customer_id = 7 AND created_at < '2026-02-01';

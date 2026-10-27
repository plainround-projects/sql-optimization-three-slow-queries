-- Step 5: a covering index for the five-column listing. INCLUDE stores the other listed
-- columns in the leaf pages, so the heap (and the wide notes column) is never visited.
-- Safe to run twice. Undo: down/003_index_listing_covering.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_listing ON orders (customer_id, created_at DESC) INCLUDE (id, status, total);
COMMIT;
-- Index-only scans need the visibility map to say the pages are all-visible (VACUUM cannot run in a transaction).
VACUUM orders;

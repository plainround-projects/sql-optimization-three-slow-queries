-- Step 5: a covering index for the five-column listing. INCLUDE stores the other listed
-- columns in the leaf pages, so the heap (and the wide notes column) is never visited.
CREATE INDEX idx_orders_listing ON orders (customer_id, created_at DESC) INCLUDE (id, status, total);
-- Index-only scans need the visibility map to say the pages are all-visible.
VACUUM orders;

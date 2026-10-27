-- Step 4: equality column first, then the sort column in the direction the query wants.
-- One customer's rows sit together, newest first, so LIMIT 10 reads ten entries and stops.
-- Safe to run twice. Undo: down/002_index_customer_created.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_customer_created ON orders (customer_id, created_at DESC);
COMMIT;

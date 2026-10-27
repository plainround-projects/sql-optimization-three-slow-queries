-- Undo migration 004: bring the narrow index back. Safe to run twice.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_customer_created ON orders (customer_id, created_at DESC);
COMMIT;

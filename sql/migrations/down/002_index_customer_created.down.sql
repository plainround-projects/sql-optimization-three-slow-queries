-- Undo migration 002. Safe to run twice.
BEGIN;
DROP INDEX IF EXISTS idx_orders_customer_created;
COMMIT;

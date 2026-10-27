-- Undo migration 001. Safe to run twice.
BEGIN;
DROP INDEX IF EXISTS idx_orders_created_at;
COMMIT;

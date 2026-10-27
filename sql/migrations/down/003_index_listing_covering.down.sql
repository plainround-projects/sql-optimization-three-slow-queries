-- Undo migration 003. Safe to run twice.
BEGIN;
DROP INDEX IF EXISTS idx_orders_listing;
COMMIT;

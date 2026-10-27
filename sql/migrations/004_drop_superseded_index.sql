-- Step 6, contract: idx_orders_listing has the same leading columns as idx_orders_customer_created, so it
-- serves query 2 as well. Keeping both pays the write cost twice for no read benefit: drop the narrow one.
-- Safe to run twice. Undo: down/004_drop_superseded_index.down.sql.
BEGIN;
DROP INDEX IF EXISTS idx_orders_customer_created;
COMMIT;

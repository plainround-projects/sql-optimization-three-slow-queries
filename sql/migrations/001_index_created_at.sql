-- Step 3: the day query becomes a range on created_at; this index is what the range seeks into.
-- Safe to run twice. Undo: down/001_index_created_at.down.sql.
BEGIN;
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at);
COMMIT;

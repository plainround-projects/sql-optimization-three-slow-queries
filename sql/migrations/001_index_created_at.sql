-- Step 3: the day query becomes a range on created_at; this index is what the range seeks into.
CREATE INDEX idx_orders_created_at ON orders (created_at);

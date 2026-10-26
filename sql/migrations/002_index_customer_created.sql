-- Step 4: equality column first, then the sort column in the direction the query wants.
-- One customer's rows sit together, newest first, so LIMIT 10 reads ten entries and stops.
CREATE INDEX idx_orders_customer_created ON orders (customer_id, created_at DESC);

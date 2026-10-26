-- Step 6: idx_orders_listing has the same leading columns as idx_orders_customer_created, so it
-- serves query 2 as well. Keeping both pays the write cost twice for no read benefit: drop the narrow one.
DROP INDEX idx_orders_customer_created;

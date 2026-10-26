-- Query 2 before, a customer with 7 orders: still a full scan, because nothing finds the customer.
SET timezone = 'UTC';
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 31337 ORDER BY created_at DESC LIMIT 10;

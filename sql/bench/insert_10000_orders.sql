-- One batch of 10,000 inserts, shaped like the seed (60% to the heavy customers, random times). The write-cost
-- measurement runs it under EXPLAIN (ANALYZE, BUFFERS, WAL) and rolls it back, once per index set.
INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int ELSE 51 + floor(random() * 49950)::int END,
       'pending', timestamp '2026-01-01' + (random() * 365) * interval '1 day', 10.00,
       repeat('customer note text - ', 20)
FROM generate_series(1, 10000);

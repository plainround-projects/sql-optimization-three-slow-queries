-- 002_seed.sql: DML. One million orders with real skew, then fresh statistics.
-- setseed makes the "random" data identical on every run, so the notes and plans repeat.
SELECT setseed(0.42);
SET timezone = 'UTC';

INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT
  CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int          -- 60% of rows go to 50 customers
       ELSE 51 + floor(random() * 49950)::int END,
  (ARRAY['pending','paid','shipped','failed'])[1 + floor(random() * 4)::int],
  timestamp '2026-01-01' + (random() * 365) * interval '1 day',
  round((random() * 500 + 5)::numeric, 2),
  repeat('customer note text - ', 20)                                  -- a deliberately wide notes column
FROM generate_series(1, 1000000);

-- 20,000 rows with a 5 KB incompressible-ish note (160 distinct md5 strings) for the TOAST demo.
INSERT INTO order_notes_demo (customer_id, status, created_at, total, notes)
SELECT 7, 'paid', timestamp '2026-01-01' + (series.n * interval '15 minutes'), 10.00,
       (SELECT string_agg(md5(series.n::text || part::text), '') FROM generate_series(1, 160) AS part)
FROM generate_series(1, 20000) AS series(n);

-- Statistics for the planner, and the visibility map that index-only scans need.
VACUUM (ANALYZE) orders;
VACUUM (ANALYZE) order_notes_demo;

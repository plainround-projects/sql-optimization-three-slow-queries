-- 001_schema.sql: DDL for the "Three slow queries" lab (PostgreSQL 18). Safe to run twice: every statement is
-- IF NOT EXISTS or idempotent, and the whole file is one transaction.
-- Only the primary key is indexed. Every other index in this project is added by a migration, one at a time,
-- after reading the plan that justifies it.
BEGIN;

CREATE TABLE IF NOT EXISTS orders (
  id          BIGSERIAL PRIMARY KEY,
  customer_id INTEGER       NOT NULL,
  status      TEXT          NOT NULL,
  created_at  TIMESTAMPTZ   NOT NULL,
  total       NUMERIC(10,2) NOT NULL,
  notes       TEXT                      -- deliberately wide: about 420 bytes a row
);

COMMENT ON TABLE  orders             IS 'One million skewed orders: 60% belong to customers 1-50.';
COMMENT ON COLUMN orders.customer_id IS 'Customers 1-50 are the heavy ones; 51-50000 get a handful each.';
COMMENT ON COLUMN orders.created_at  IS 'Spans exactly one year (2026) so the day query has data to find.';
COMMENT ON COLUMN orders.notes       IS 'Wide free text the listing never shows; makes every heap page hold fewer rows.';

-- A small second table for the "why does a big text column cost so much" experiment.
-- Its notes column is stored out of line (TOAST), which the 420-byte notes above never are.
CREATE TABLE IF NOT EXISTS order_notes_demo (
  id          BIGSERIAL PRIMARY KEY,
  customer_id INTEGER       NOT NULL,
  status      TEXT          NOT NULL,
  created_at  TIMESTAMPTZ   NOT NULL,
  total       NUMERIC(10,2) NOT NULL,
  notes       TEXT
);
ALTER TABLE order_notes_demo ALTER COLUMN notes SET STORAGE EXTERNAL;   -- out of line, uncompressed
COMMENT ON TABLE order_notes_demo IS '20,000 orders whose 5 KB notes live in the TOAST table.';

COMMIT;

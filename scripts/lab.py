"""Small helpers shared by run_lesson.py and the tests: connect, run SQL files, read plans."""
import json
import os
import re
import statistics
import time
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
EXPLAIN_DIR = SQL_DIR / "explain"
MIGRATIONS = sorted((SQL_DIR / "migrations").glob("*.sql"))
LESSON_INDEXES = ["idx_orders_created_at", "idx_orders_customer_created", "idx_orders_listing"]


def connect(autocommit=True):
    """Connection from the PG* variables (the same ones psql and the Makefile use).

    Parallel query is switched off for the session so plans read the same on the compose database
    and on a CI service container, whose server defaults differ.
    """
    return psycopg.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "55431"),
        user=os.environ.get("PGUSER", "lab"),
        password=os.environ.get("PGPASSWORD", "lab"),
        dbname=os.environ.get("PGDATABASE", "lab"),
        options="-c max_parallel_workers_per_gather=0",
        autocommit=autocommit,
    )


def split_statements(sql_text):
    """Split a SQL file on semicolons, ignoring comments and quoted text."""
    without_comments = re.sub(r"--[^\n]*", "", sql_text)
    statements, current, quote = [], [], None
    for character in without_comments:
        if quote:
            quote = None if character == quote else quote
        elif character in ("'", '"'):
            quote = character
        elif character == ";":
            statements.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    return [statement for statement in statements if statement]


def run_file(connection, path):
    """Run every statement of a file on one connection; return the rows of the last one that returns rows."""
    rows = []
    for statement in split_statements(Path(path).read_text()):
        cursor = connection.execute(statement)
        if cursor.description:
            rows = cursor.fetchall()
    return rows


def plan_lines(connection, path):
    """Run an explain/*.sql file and return the plan as text lines."""
    return [row[0] for row in run_file(connection, path)]


def execution_ms(lines):
    return float(re.search(r"Execution Time: ([\d.]+) ms", "\n".join(lines)).group(1))


def buffers_touched(lines):
    """Pages a plan touched: the top node's 'Buffers: shared hit=.. read=..' plus the pages read to send
    the rows to the client (the line after 'Serialization:'), where out-of-line TOAST values are fetched."""
    total, after_serialization = 0, False
    for line in lines:
        match = re.search(r"Buffers: shared (.*)", line)
        if line.startswith("Serialization:"):
            after_serialization = True
        elif match and (after_serialization or total == 0):
            total += sum(int(count) for count in re.findall(r"(?:hit|read)=(\d+)", match.group(1)))
            after_serialization = False
    return total


def explain_json(connection, query):
    """Plan of a query as the JSON tree PostgreSQL returns, with real timings and buffers."""
    cursor = connection.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)
    return cursor.fetchone()[0][0]


def plan_nodes(plan):
    """Every node of a JSON plan, parent first."""
    node = plan.get("Plan", plan)
    yield node
    for child in node.get("Plans", []):
        yield from plan_nodes(child)


def node_types(plan):
    return [node["Node Type"] for node in plan_nodes(plan)]


def drop_lesson_indexes(connection):
    for index in LESSON_INDEXES:
        connection.execute(f"DROP INDEX IF EXISTS {index}")


def reset_to(connection, step):
    """Put the table in the state after migration number `step` (0 means only the primary key)."""
    drop_lesson_indexes(connection)
    for migration in MIGRATIONS[:step]:
        run_file(connection, migration)
    connection.execute("ANALYZE orders")


def median(values):
    return statistics.median(values)


WRITE_BATCH = """
INSERT INTO orders (customer_id, status, created_at, total, notes)
SELECT CASE WHEN random() < 0.6 THEN 1 + floor(random() * 50)::int ELSE 51 + floor(random() * 49950)::int END,
       'pending', timestamp '2026-01-01' + (random() * 365) * interval '1 day', 10.00,
       repeat('customer note text - ', 20)
FROM generate_series(1, 10000)
"""


def measure_write_cost(repetitions=5):
    """Insert 10,000 orders `repetitions` times under EXPLAIN (ANALYZE, BUFFERS, WAL), rolling each batch back.

    Returns medians: milliseconds, pages touched, WAL records and WAL bytes. Pages touched and WAL records
    are the stable numbers (every index adds about 10,000 of each); milliseconds and bytes vary by machine.
    """
    samples = {"milliseconds": [], "buffers": [], "wal_records": [], "wal_bytes": []}
    with connect(autocommit=False) as connection:
        for attempt in range(repetitions + 1):         # attempt 0 is a warm-up, not recorded
            lines = [row[0] for row in connection.execute("EXPLAIN (ANALYZE, BUFFERS, WAL) " + WRITE_BATCH)]
            connection.rollback()
            if not attempt:
                continue
            wal = re.search(r"WAL: records=(\d+).* bytes=(\d+)", "\n".join(lines))
            samples["milliseconds"].append(execution_ms(lines))
            samples["buffers"].append(buffers_touched(lines))
            samples["wal_records"].append(int(wal.group(1)))
            samples["wal_bytes"].append(int(wal.group(2)))
    return {name: median(values) for name, values in samples.items()}


def row_count(connection):
    return connection.execute("SELECT count(*) FROM orders").fetchone()[0]

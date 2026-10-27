"""One test per "Done when" line of the lesson, against the seeded database (make up db first)."""

import pathlib

import pytest

from slow_queries.domain.errors import UnknownStepError
from slow_queries.domain.plan import parse_text_plan
from slow_queries.infrastructure.lab_database import PostgresLabDatabase
from slow_queries.infrastructure.sql_script import run_file

pytestmark = pytest.mark.integration

DAY_RANGE = "SELECT * FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15'"
DAY_FUNCTION = "SELECT * FROM orders WHERE date(created_at) = '2026-03-14'"
LATEST = "SELECT * FROM orders WHERE customer_id = {customer} ORDER BY created_at DESC LIMIT 10"
LISTING = (
    "FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' "
    "ORDER BY created_at DESC"
)
LISTING_WIDE = "SELECT * " + LISTING
LISTING_NARROW = "SELECT id, customer_id, status, created_at, total " + LISTING
SMALL_CUSTOMER = 31337


def test_the_seed_has_the_intended_skew_and_fresh_statistics(connection):
    total, heavy = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50) FROM orders"
    ).fetchone()
    assert total == 1_000_000
    assert 0.55 <= heavy / total <= 0.65, "customers 1-50 should hold about 60% of the rows"
    biggest, typical = connection.execute(
        "SELECT max(orders), percentile_cont(0.5) WITHIN GROUP (ORDER BY orders) "
        "FROM (SELECT count(*) AS orders FROM orders GROUP BY customer_id) AS per_customer"
    ).fetchone()
    assert biggest > 10_000
    assert typical < 20
    analyzed = connection.execute(
        "SELECT coalesce(last_analyze, last_autoanalyze) FROM pg_stat_user_tables WHERE relname = 'orders'"
    ).fetchone()[0]
    assert analyzed is not None, "statistics must be fresh before any plan is trusted"


def test_a_function_on_the_column_forces_a_full_scan_that_discards_almost_every_row(database):
    plan = database.explain_json(DAY_FUNCTION)
    assert plan.has_node("Seq Scan")
    assert plan.rows_removed_by_filter > 990_000


def test_the_day_query_uses_the_index_and_is_ten_times_faster(database):
    before = database.explain_json(DAY_FUNCTION)
    database.apply_step(1)
    after = database.explain_json(DAY_RANGE)
    assert not after.has_node("Seq Scan")
    assert after.uses_index("idx_orders_created_at")
    assert before.execution_ms >= 10 * after.execution_ms
    assert before.pages >= 10 * after.pages, "the page count tells the same story as the clock"


@pytest.mark.parametrize("customer", [7, SMALL_CUSTOMER])
def test_latest_orders_read_ten_index_entries_with_no_sort_for_heavy_and_small_customers(
    database, connection, customer
):
    database.reset_to(2)
    plan = database.explain_json(LATEST.format(customer=customer))
    assert not plan.has_node("Sort"), f"customer {customer} still sorts"
    assert plan.uses_index("idx_orders_customer_created")
    assert plan.pages <= 20, "ten index entries and their rows, whatever the customer's total"
    returned = connection.execute(LATEST.format(customer=customer)).fetchall()
    expected = connection.execute("SELECT least(10, count(*)) FROM orders WHERE customer_id = %s", (customer,))
    assert len(returned) == expected.fetchone()[0]


def test_a_covering_index_gives_an_index_only_scan_with_fewer_pages(database):
    database.reset_to(2)
    wide = database.explain_json(LISTING_WIDE)
    database.apply_step(3)
    narrow = database.explain_json(LISTING_NARROW)
    assert narrow.has_node("Index Only Scan")
    assert narrow.heap_fetches == 0, "the visibility map is current, so the heap is never visited"
    assert narrow.pages * 1.5 < wide.pages


def test_a_big_out_of_line_column_costs_pages_only_when_it_is_selected(database):
    wide = parse_text_plan(database.capture_plan("q3_toast_wide"))
    narrow = parse_text_plan(database.capture_plan("q3_toast_narrow"))
    assert wide.pages > 20 * narrow.pages, "detoasting reads the TOAST table"


def test_each_index_adds_write_work_and_the_batches_are_rolled_back(database):
    rows_before = database.row_count()
    bare = database.measure_write_cost(repetitions=2)
    database.reset_to(2)
    two_indexes = database.measure_write_cost(repetitions=2)
    database.reset_to(4)
    after_drop = database.measure_write_cost(repetitions=2)
    assert two_indexes.wal_records >= bare.wal_records + 2 * 9_000, "about 10,000 records per index"
    assert two_indexes.pages > bare.pages
    assert bare.wal_records < after_drop.wal_records < two_indexes.wal_records + 1_000
    assert database.row_count() == rows_before


def test_the_committed_plans_say_what_the_readme_says():
    explain = pathlib.Path(__file__).resolve().parents[2] / "sql" / "explain"

    def plan(name):
        return parse_text_plan((explain / f"{name}.txt").read_text().splitlines())

    assert plan("q1_day_before").has_node("Seq Scan")
    assert plan("q1_day_after").uses_index("idx_orders_created_at")
    assert plan("q2_latest_whale_before").has_node("Sort")
    assert not plan("q2_latest_whale_after").has_node("Sort")
    assert plan("q3_listing_after").uses_index("idx_orders_listing")


def test_migrations_can_run_twice_and_be_reverted_twice_without_harm(database):
    for number in (1, 2, 3, 4):
        database.apply_step(number)
        database.apply_step(number)
    assert set(database.index_sizes()) == {"orders_pkey", "idx_orders_created_at", "idx_orders_listing"}
    database.revert_step(4)
    database.revert_step(4)
    assert "idx_orders_customer_created" in database.index_sizes(), "down 004 brings the narrow index back"
    for number in (3, 2, 1):
        database.revert_step(number)
        database.revert_step(number)
    assert set(database.index_sizes()) == {"orders_pkey"}


def test_the_seed_script_leaves_tables_that_have_rows_alone():
    seed = (pathlib.Path(__file__).resolve().parents[2] / "sql" / "002_seed.sql").read_text()
    assert "\\if :orders_empty" in seed
    assert "\\if :demo_empty" in seed


def test_a_step_the_lesson_does_not_have_is_refused(database):
    with pytest.raises(UnknownStepError):
        database.apply_step(5)
    with pytest.raises(UnknownStepError):
        database.revert_step(0)


def test_the_schema_script_can_run_twice(connection, settings):
    run_file(connection, settings.sql_dir / "001_schema.sql")
    run_file(connection, settings.sql_dir / "001_schema.sql")
    assert connection.execute("SELECT count(*) FROM orders").fetchone()[0] == 1_000_000


def test_the_adapter_is_usable_as_the_port(database: PostgresLabDatabase):
    assert len(database.migrations()) == len(database.down_migrations()) == 4

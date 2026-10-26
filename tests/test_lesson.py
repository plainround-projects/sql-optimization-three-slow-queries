"""One test per "Done when" line of the lesson. They run against the compose database after `make db`."""
import lab

DAY_RANGE = "SELECT * FROM orders WHERE created_at >= '2026-03-14' AND created_at < '2026-03-15'"
DAY_FUNCTION = "SELECT * FROM orders WHERE date(created_at) = '2026-03-14'"
LATEST = "SELECT * FROM orders WHERE customer_id = {customer} ORDER BY created_at DESC LIMIT 10"
LISTING = ("FROM orders WHERE customer_id = 7 AND created_at >= '2026-03-01' AND created_at < '2026-04-01' "
           "ORDER BY created_at DESC")
LISTING_WIDE = "SELECT * " + LISTING
LISTING_NARROW = "SELECT id, customer_id, status, created_at, total " + LISTING
SMALL_CUSTOMER = 31337


def total_buffers(plan):
    return plan["Plan"]["Shared Hit Blocks"] + plan["Plan"]["Shared Read Blocks"]


def test_step1_seed_has_the_intended_skew_and_fresh_statistics(connection):
    total, whale_rows = connection.execute(
        "SELECT count(*), count(*) FILTER (WHERE customer_id BETWEEN 1 AND 50) FROM orders").fetchone()
    assert total == 1_000_000
    assert 0.55 <= whale_rows / total <= 0.65, "customers 1-50 should hold about 60% of the rows"
    biggest, typical = connection.execute(
        "SELECT max(orders), percentile_cont(0.5) WITHIN GROUP (ORDER BY orders) "
        "FROM (SELECT count(*) AS orders FROM orders GROUP BY customer_id) AS per_customer").fetchone()
    assert biggest > 10_000 and typical < 20
    analyzed = connection.execute(
        "SELECT coalesce(last_analyze, last_autoanalyze) FROM pg_stat_user_tables WHERE relname = 'orders'").fetchone()[0]
    assert analyzed is not None, "statistics must be fresh before any plan is trusted"


def test_step2_the_function_on_the_column_forces_a_full_scan(connection, at_step):
    at_step(0)
    plan = lab.explain_json(connection, DAY_FUNCTION)
    root = plan["Plan"]
    assert root["Node Type"] == "Seq Scan"
    assert root["Rows Removed by Filter"] > 990_000, "it reads and throws away almost every row"
    assert 2000 < root["Actual Rows"] < 3500, "the day really holds about 2,700 orders"


def test_step3_day_query_uses_the_index_and_is_ten_times_faster(connection, at_step):
    at_step(0)
    before = lab.explain_json(connection, DAY_FUNCTION)
    at_step(1)
    after = lab.explain_json(connection, DAY_RANGE)
    assert "Seq Scan" not in lab.node_types(after)
    assert any(node.get("Index Name") == "idx_orders_created_at" for node in lab.plan_nodes(after))
    assert before["Execution Time"] >= 10 * after["Execution Time"]
    assert total_buffers(before) >= 10 * total_buffers(after), "the page count tells the same story as the clock"


def test_step4_latest_orders_read_ten_entries_with_no_sort_for_small_and_large_customers(connection, at_step):
    at_step(2)
    for customer, expected_rows in ((7, 10), (SMALL_CUSTOMER, None)):
        plan = lab.explain_json(connection, LATEST.format(customer=customer))
        assert "Sort" not in lab.node_types(plan), f"customer {customer} still sorts"
        assert any(node.get("Index Name") == "idx_orders_customer_created" for node in lab.plan_nodes(plan))
        returned = plan["Plan"]["Actual Rows"]
        assert returned == (expected_rows or connection.execute(
            "SELECT least(10, count(*)) FROM orders WHERE customer_id = %s", (customer,)).fetchone()[0])
        assert total_buffers(plan) <= 20, "ten index entries and their rows, whatever the customer's total"


def test_step5_covering_index_gives_an_index_only_scan_with_fewer_pages(connection, at_step):
    at_step(2)
    wide = lab.explain_json(connection, LISTING_WIDE)
    at_step(3)
    narrow = lab.explain_json(connection, LISTING_NARROW)
    assert "Index Only Scan" in lab.node_types(narrow)
    only_scan = next(node for node in lab.plan_nodes(narrow) if node["Node Type"] == "Index Only Scan")
    assert only_scan["Heap Fetches"] == 0, "the visibility map is current, so the heap is never visited"
    assert total_buffers(narrow) * 1.5 < total_buffers(wide)


def test_step5_a_big_out_of_line_column_costs_pages_only_when_it_is_selected(connection):
    wide, narrow = [
        lab.plan_lines(connection, lab.EXPLAIN_DIR / f"q3_toast_{name}.sql") for name in ("wide", "narrow")]
    assert lab.buffers_touched(wide) > 20 * lab.buffers_touched(narrow), "detoasting reads the TOAST table"


def test_step6_each_index_adds_write_work_and_the_batches_are_rolled_back(connection, at_step):
    rows_before = lab.row_count(connection)
    at_step(0)
    bare = lab.measure_write_cost(repetitions=2)
    at_step(2)
    two_indexes = lab.measure_write_cost(repetitions=2)
    at_step(4)
    after_drop = lab.measure_write_cost(repetitions=2)
    assert two_indexes["wal_records"] >= bare["wal_records"] + 2 * 9_000, "about 10,000 records per index"
    assert two_indexes["buffers"] > bare["buffers"]
    assert after_drop["wal_records"] < two_indexes["wal_records"] + 1_000 and after_drop["wal_records"] > bare["wal_records"]
    assert lab.row_count(connection) == rows_before


def test_the_captured_plans_in_the_repository_match_the_story(connection):
    """The .txt files committed under sql/explain/ are real runs: spot-check the first and last of each query."""
    text = lambda name: (lab.EXPLAIN_DIR / f"{name}.txt").read_text()
    assert "Seq Scan on orders" in text("q1_day_before") and "idx_orders_created_at" in text("q1_day_after")
    assert "Sort" in text("q2_latest_whale_before") and "Sort" not in text("q2_latest_whale_after")
    assert "Index Only Scan using idx_orders_listing" in text("q3_listing_after")

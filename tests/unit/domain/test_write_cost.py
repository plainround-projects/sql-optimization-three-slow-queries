import pytest

from slow_queries.domain.errors import PlanParseError
from slow_queries.domain.write_cost import WriteCost, median_cost, parse_write_cost

INSERT_PLAN = [
    "Insert on orders  (cost=0.00..1.00 rows=0 width=0) (actual time=40.1..40.1 rows=0.00 loops=1)",
    "  Buffers: shared hit=31412 dirtied=2000",
    "  WAL: records=20330 fpi=10 bytes=5900000",
    "Execution Time: 41.8 ms",
]


def test_an_insert_plan_gives_time_pages_and_wal():
    assert parse_write_cost(INSERT_PLAN) == WriteCost(41.8, 31412, 20330, 5_900_000)


def test_a_plan_without_wal_is_refused():
    with pytest.raises(PlanParseError, match="WAL"):
        parse_write_cost(["Insert on orders", "Execution Time: 1.0 ms"])


def test_the_median_is_taken_per_figure():
    samples = [WriteCost(10, 100, 1000, 5000), WriteCost(30, 300, 3000, 9000), WriteCost(20, 200, 2000, 7000)]
    assert median_cost(samples) == WriteCost(20, 200, 2000, 7000)


def test_the_median_of_nothing_is_an_error():
    with pytest.raises(ValueError, match="at least one"):
        median_cost([])

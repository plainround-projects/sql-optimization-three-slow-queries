from slow_queries.application.replay import LessonResult
from slow_queries.application.report import render_results
from slow_queries.domain import lesson
from slow_queries.domain.plan import PlanSummary
from slow_queries.domain.write_cost import WriteCost


def result() -> LessonResult:
    plans = {}
    for name in [*lesson.BEFORE_ANY_INDEX, *(n for step in lesson.STEPS for n in step.captures)]:
        slow = name.endswith(("before", "wide"))
        plans[name] = PlanSummary(400.0 if slow else 4.0, 60000 if slow else 3000, (), (), 0, None)
    return LessonResult(plans, (("no new indexes", WriteCost(42.5, 31000, 20000, 5_900_000)),), {"idx_a": 22_500_000})


def test_the_comparison_table_has_a_row_per_query_with_the_speedup():
    text = render_results(result())
    assert "| q1 day query | 400.000 | 4.000 | 100x | 60000 | 3000 |" in text


def test_the_write_cost_table_and_index_sizes_follow():
    text = render_results(result())
    assert "| no new indexes | 42.5 | 31000 | 20000 | 5.9 |" in text
    assert "| idx_a | 22.5 |" in text


def test_the_host_load_note_is_printed_when_it_is_known():
    from dataclasses import replace

    from slow_queries.domain.host import HostLoad

    text = render_results(replace(result(), host_load=HostLoad(40.0, 12)))
    assert "Measured on a loaded machine (load average 40.0 on 12 CPUs)" in text
    assert "Measured" not in render_results(result())

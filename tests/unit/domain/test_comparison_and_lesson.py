from slow_queries.domain import lesson
from slow_queries.domain.comparison import Improvement
from slow_queries.domain.plan import PlanSummary


def plan(ms: float, pages: int) -> PlanSummary:
    return PlanSummary(ms, pages, (), (), 0, None)


def test_speedup_and_pages_ratio_compare_before_with_after():
    improvement = Improvement(plan(400.0, 60000), plan(4.0, 3000))
    assert improvement.speedup == 100.0
    assert improvement.pages_ratio == 20.0


def test_a_zero_millisecond_result_does_not_divide_by_zero():
    improvement = Improvement(plan(1.0, 10), plan(0.0, 0))
    assert improvement.speedup == 1000.0
    assert improvement.pages_ratio == 10.0


def test_every_comparison_names_plans_the_replay_captures():
    captured = set(lesson.BEFORE_ANY_INDEX)
    for step in lesson.STEPS:
        captured |= set(step.captures)
    for _label, before, after in lesson.COMPARISONS:
        assert {before, after} <= captured


def test_the_steps_are_numbered_from_one_without_gaps():
    assert [step.number for step in lesson.STEPS] == [1, 2, 3, 4]

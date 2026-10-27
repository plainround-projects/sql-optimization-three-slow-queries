import pytest

from slow_queries.application.replay import ReplayLesson
from slow_queries.domain import lesson
from slow_queries.domain.errors import LessonInterruptedError

from .fakes import FakeDatabase, RecordingStore


def run(database: FakeDatabase | None = None, **options):
    database = database or FakeDatabase()
    store = RecordingStore()
    result = ReplayLesson(database, store, **options).run()
    return database, store, result


def test_the_lesson_starts_from_the_primary_key_alone():
    database, _store, _result = run()
    assert database.calls[0] == "reset_to 0"


def test_plans_before_any_index_are_read_before_the_first_migration():
    database, _store, _result = run()
    first_step = database.calls.index("apply_step 1")
    captured_before = [call for call in database.calls[:first_step] if call.startswith("capture")]
    assert captured_before == [f"capture {name}" for name in lesson.BEFORE_ANY_INDEX]


def test_each_step_is_applied_then_read_then_costed_then_vacuumed_in_order():
    database, _store, _result = run()
    assert database.calls[database.calls.index("apply_step 2") :][:7] == [
        "apply_step 2",
        "capture q2_latest_whale_after",
        "capture q2_latest_small_after",
        "capture q3_listing_before",
        "capture q3_listing_narrow",
        "measure 5",
        "vacuum",
    ]


def test_every_plan_is_saved_and_summarized():
    _database, store, result = run()
    expected = set(lesson.BEFORE_ANY_INDEX) | {name for step in lesson.STEPS for name in step.captures}
    assert set(store.plans) == expected == set(result.plans)
    assert result.plans["q1_day_before"].execution_ms == 10.0


def test_the_write_cost_of_each_index_set_is_recorded_including_the_empty_set():
    _database, _store, result = run(repetitions=3)
    labels = [label for label, _cost in result.write_costs]
    assert labels[0] == "no new indexes"
    assert labels[1:] == [step.label for step in lesson.STEPS]


def test_the_notes_are_saved_once_at_the_end():
    _database, store, _result = run()
    assert store.report is not None
    assert store.report.startswith("# Results of the last")


def test_a_changed_row_count_means_a_write_batch_was_not_rolled_back():
    with pytest.raises(AssertionError, match="rolled back"):
        run(FakeDatabase(rows=1000, rows_after=1500))


def test_a_stop_request_ends_the_replay_between_steps_without_saving_notes():
    database, store, calls = FakeDatabase(), RecordingStore(), []

    def should_stop() -> bool:
        calls.append(1)
        return len(calls) > 8

    with pytest.raises(LessonInterruptedError):
        ReplayLesson(database, store, should_stop=should_stop).run()
    assert store.report is None
    assert "apply_step 4" not in database.calls


def test_progress_is_reported_for_each_step_and_plan():
    messages: list[str] = []
    run(progress=messages.append)
    assert "step 1: + idx_orders_created_at" in messages
    assert any(message.startswith("plan q1_day_before") for message in messages)

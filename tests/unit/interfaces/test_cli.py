import pytest

from slow_queries.application.health import ProbeFailedError
from slow_queries.interfaces import health_cli, run_cli

from ..application.fakes import FakeDatabase, RecordingStore


def test_a_missing_password_is_a_configuration_error_with_exit_code_2(monkeypatch, capsys):
    monkeypatch.delenv("PGPASSWORD", raising=False)
    assert health_cli.main([]) == 2
    assert "PGPASSWORD" in capsys.readouterr().err
    assert run_cli.main([]) == 2


def test_the_run_command_replays_against_the_database_it_is_given(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")
    monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda _settings, _sql_dir: FakeDatabase())
    assert run_cli.main(["--output-dir", str(tmp_path), "--repetitions", "2"]) == 0
    assert (tmp_path / "results.md").exists()
    assert (tmp_path / "q1_day_before.txt").exists()
    assert "no new indexes" in capsys.readouterr().out


def test_a_stop_request_gives_exit_code_130(monkeypatch, tmp_path):
    monkeypatch.setenv("PGPASSWORD", "x")
    monkeypatch.setattr(run_cli, "PostgresLabDatabase", lambda _settings, _sql_dir: FakeDatabase())

    class AlreadyStopped:
        requested = True

        def install(self) -> None:
            pass

    monkeypatch.setattr(run_cli, "ShutdownSignal", AlreadyStopped)
    assert run_cli.main(["--output-dir", str(tmp_path)]) == 130


def test_health_is_exit_1_when_the_probe_fails(monkeypatch, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")

    class Failing:
        name = "postgres"

        def __init__(self, _settings) -> None:
            pass

        def check(self) -> str:
            raise ProbeFailedError("the orders table is missing; run make db")

    monkeypatch.setattr(health_cli, "PostgresOrdersProbe", Failing)
    assert health_cli.main([]) == 1
    assert "FAIL postgres: the orders table is missing" in capsys.readouterr().out


def test_health_is_exit_0_when_the_probe_passes(monkeypatch, capsys):
    monkeypatch.setenv("PGPASSWORD", "x")

    class Passing:
        name = "postgres"

        def __init__(self, _settings) -> None:
            pass

        def check(self) -> str:
            return "1,000,000 orders, statistics fresh"

    monkeypatch.setattr(health_cli, "PostgresOrdersProbe", Passing)
    assert health_cli.main([]) == 0
    assert "ok postgres" in capsys.readouterr().out


@pytest.mark.parametrize("argument", ["--repetitions", "x"])
def test_a_bad_argument_is_rejected_by_the_parser(argument):
    with pytest.raises(SystemExit):
        run_cli.main([argument])


def test_the_recording_store_is_usable_as_a_port():
    store = RecordingStore()
    store.save_plan("a", ["x"])
    assert store.plans == {"a": ("x",)}

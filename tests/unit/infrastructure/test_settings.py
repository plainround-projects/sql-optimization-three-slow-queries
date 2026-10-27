import pytest

from slow_queries.infrastructure.settings import ConfigurationError, Settings

MINIMAL = {"PGPASSWORD": "s3cret-value"}


def test_defaults_describe_the_local_compose_setup():
    settings = Settings.from_env(MINIMAL)
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("localhost", 55431, "lab", "lab")
    assert (postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == (5, 120_000)
    assert postgres.max_parallel_workers_per_gather == 0
    assert settings.log_level == "INFO"
    assert settings.sql_dir.name == "sql"


def test_the_database_password_has_no_default():
    with pytest.raises(ConfigurationError, match="PGPASSWORD"):
        Settings.from_env({})


def test_the_password_never_appears_in_a_printed_settings_object():
    assert "s3cret-value" not in repr(Settings.from_env(MINIMAL))


def test_every_variable_can_be_overridden():
    settings = Settings.from_env(
        {
            **MINIMAL,
            "PGHOST": "db",
            "PGPORT": "6543",
            "PGDATABASE": "x",
            "PGUSER": "u",
            "PG_CONNECT_TIMEOUT_SECONDS": "2",
            "PG_STATEMENT_TIMEOUT_MS": "500",
            "PG_PARALLEL_WORKERS_PER_GATHER": "2",
            "LAB_SQL_DIR": "/somewhere/sql",
            "LOG_LEVEL": "debug",
        }
    )
    postgres = settings.postgres
    assert (postgres.host, postgres.port, postgres.database, postgres.user) == ("db", 6543, "x", "u")
    assert (postgres.connect_timeout_seconds, postgres.statement_timeout_ms) == (2, 500)
    assert postgres.max_parallel_workers_per_gather == 2
    assert (postgres.password, settings.log_level, str(settings.sql_dir)) == ("s3cret-value", "DEBUG", "/somewhere/sql")


@pytest.mark.parametrize(
    "extra",
    [
        {"PGPORT": "0"},
        {"PGPORT": "five"},
        {"PGHOST": "  "},
        {"PG_STATEMENT_TIMEOUT_MS": "-1"},
        {"PG_PARALLEL_WORKERS_PER_GATHER": "-1"},
        {"LOG_LEVEL": "LOUD"},
    ],
)
def test_an_unusable_value_is_rejected_with_the_variable_name(extra):
    with pytest.raises(ConfigurationError, match=next(iter(extra))):
        Settings.from_env({**MINIMAL, **extra})


def test_settings_read_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "from-the-process")
    assert Settings.from_env().postgres.password == "from-the-process"

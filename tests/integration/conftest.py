"""Fixtures for the tests that need the seeded database from `make up db`."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from slow_queries.infrastructure import postgres
from slow_queries.infrastructure.lab_database import PostgresLabDatabase
from slow_queries.infrastructure.settings import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def database(settings: Settings) -> Iterator[PostgresLabDatabase]:
    """The lab database; every test starts and ends with only the primary key in place."""
    lab = PostgresLabDatabase(settings.postgres, settings.sql_dir)
    lab.reset_to(0)
    yield lab
    lab.reset_to(0)


@pytest.fixture
def connection(settings: Settings) -> Iterator[psycopg.Connection[Any]]:
    with postgres.session(settings.postgres) as live:
        yield live

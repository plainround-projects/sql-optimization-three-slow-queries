"""Adapter: the health check of the one dependency, PostgreSQL."""

from __future__ import annotations

import psycopg

from ..application.health import ProbeFailedError
from .postgres import scalar, session
from .settings import PostgresSettings


class PostgresOrdersProbe:
    """Healthy when PostgreSQL answers and the seeded orders table has rows and fresh statistics."""

    name = "postgres"

    def __init__(self, settings: PostgresSettings) -> None:
        self._settings = settings

    def check(self) -> str:
        try:
            with session(self._settings) as connection:
                if scalar(connection, "SELECT to_regclass('public.orders')") is None:
                    raise ProbeFailedError("the orders table is missing; run make db")
                rows = scalar(connection, "SELECT count(*) FROM orders")
                analyzed = scalar(
                    connection,
                    "SELECT coalesce(last_analyze, last_autoanalyze) FROM pg_stat_user_tables WHERE relname = 'orders'",
                )
        except psycopg.Error as error:
            raise ProbeFailedError(f"cannot query PostgreSQL: {error}") from error
        if rows == 0:
            raise ProbeFailedError("the orders table is empty; run make db")
        if analyzed is None:
            raise ProbeFailedError("the orders table has never been analyzed; run make db")
        return f"{rows:,} orders, statistics fresh"

"""Configuration from the environment, validated once at startup (twelve-factor). Secrets only from here."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty (copy .env.example to .env)")
    return value


def _non_negative_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, str(default)).strip()
    if not raw.isdigit():
        raise ConfigurationError(f"{name} must be a non-negative integer, got {raw!r}")
    return int(raw)


def _positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    value = _non_negative_int(environ, name, default)
    if value < 1:
        raise ConfigurationError(f"{name} must be at least 1, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class PostgresSettings:
    """The PostgreSQL part of the configuration; the password is never printed."""

    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    connect_timeout_seconds: int
    statement_timeout_ms: int
    max_parallel_workers_per_gather: int


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres: PostgresSettings
    sql_dir: Path
    log_level: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Read and validate the environment; raises `ConfigurationError` naming the first bad variable."""
        env = os.environ if environ is None else environ
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        default_sql = Path(__file__).resolve().parents[3] / "sql"
        sql_dir = Path(_text(env, "LAB_SQL_DIR", str(default_sql)))
        return cls(
            postgres=PostgresSettings(
                host=_text(env, "PGHOST", "localhost"),
                port=_positive_int(env, "PGPORT", 55431),
                database=_text(env, "PGDATABASE", "lab"),
                user=_text(env, "PGUSER", "lab"),
                password=_text(env, "PGPASSWORD"),
                connect_timeout_seconds=_positive_int(env, "PG_CONNECT_TIMEOUT_SECONDS", 5),
                statement_timeout_ms=_positive_int(env, "PG_STATEMENT_TIMEOUT_MS", 120_000),
                max_parallel_workers_per_gather=_non_negative_int(env, "PG_PARALLEL_WORKERS_PER_GATHER", 0),
            ),
            sql_dir=sql_dir,
            log_level=level,
        )

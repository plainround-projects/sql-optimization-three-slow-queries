# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-27

### Added

- PostgreSQL 18 in `docker-compose.yml`, run under an init process with a health check over TCP.
- SQL: an idempotent schema and a skewed one-million-row seed that leaves a populated table alone, the lesson's queries, four idempotent transactional migrations with down scripts, a reset script, and `EXPLAIN (ANALYZE, BUFFERS)` plans before and after each change as `.sql` plus captured `.txt`.
- A layered Python package (`domain`, `application`, `infrastructure`, `interfaces`) with the dependency rule enforced by import-linter: plan parsing and the write-cost model as pure domain code, the replay as a use case over ports, a PostgreSQL adapter, a replay command and a health command.
- Unit, integration and end-to-end tests with coverage (domain and application at 100%); ruff, mypy `strict`, import-linter and `pip-audit` in CI; hashed lock files.

# 0001. Plan parsing is pure domain code; PostgreSQL sits behind one port

Status: accepted, 2026-10-27

## Context

The lesson is about reading plans. The numbers that matter (execution time, pages touched, whether a `Sort` node is there, which index was read) all come out of `EXPLAIN` text or JSON. The first version of this repository parsed them inside helpers that also held the database connection, so nothing about the lesson could be tested without a seeded database and a minute of waiting.

## Decision

Parsing and arithmetic live in `domain/` (`plan.py`, `write_cost.py`, `comparison.py`) and never import a database driver; `application/` replays the lesson against a `LabDatabase` port; `infrastructure/lab_database.py` is the only module that talks to PostgreSQL. An import-linter contract fails the build if `domain` or `application` import `psycopg`.

## Consequences

- The domain and the replay are covered at 100% by unit tests that run in under a second and need no Docker.
- The same `parse_text_plan` reads the committed `.txt` plans and the live ones, so the README's claims about the committed files are tested.
- The port is wider than the lesson strictly needs (`reset_to`, `apply_step`, `capture_plan`, `measure_write_cost`, `vacuum`, `row_count`, `index_sizes`). That is the price of keeping SQL execution out of the use case; each method is one thing the lesson does to the table.
- SQL stays in `sql/` as files; Python runs only the migration and `explain` files, never SQL written inline in a use case.

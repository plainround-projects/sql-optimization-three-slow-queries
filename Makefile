# Commands for the lab. `make up`, `make db`, `make run`, `make test`, `make down` are all you need.
-include .env
PGHOST ?= localhost
PGPORT ?= 55431
PGUSER ?= lab
PGPASSWORD ?= lab
PGDATABASE ?= lab
export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE

# How SQL files reach the server. CI overrides this with a plain `psql` on the runner.
PSQL ?= docker compose exec -T db psql -X -q -v ON_ERROR_STOP=1 -U $(PGUSER) -d $(PGDATABASE)

VENV := .venv
PYTHON := $(VENV)/bin/python

.PHONY: up db run test psql down

$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --quiet -r requirements.txt
	touch $@

up:
	docker compose up -d --wait

# Schema, seed (about a minute), then the lesson's queries in their slow form.
db:
	$(PSQL) < sql/001_schema.sql
	$(PSQL) < sql/002_seed.sql
	$(PSQL) < sql/003_queries.sql

# Replays the lesson: plan before, one change, plan after, and the write cost of each index.
run: $(VENV)/.installed
	$(PYTHON) scripts/run_lesson.py

test: $(VENV)/.installed
	$(PYTHON) -m pytest

psql:
	docker compose exec db psql -U $(PGUSER) -d $(PGDATABASE)

# -v removes the volume too, so the next `make up` starts from an empty database.
down:
	docker compose down -v

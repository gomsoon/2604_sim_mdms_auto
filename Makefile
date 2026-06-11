PYTHON := .venv/bin/python
PIP := .venv/bin/pip
FLASK := .venv/bin/flask
ALEMBIC := .venv/bin/alembic
COVERAGE_TOTAL_MIN := 80
COVERAGE_STATEMENT_MIN := 88.5
COVERAGE_BRANCH_MIN := 75.0
COVERAGE_JSON := /tmp/mdms_coverage_summary.json

.PHONY: install init-db db-current db-history seed-demo run test test-functional

install:
	$(PIP) install -e .[dev]

init-db:
	$(FLASK) --app wsgi:app init-db

db-current:
	$(ALEMBIC) current

db-history:
	$(ALEMBIC) history

seed-demo:
	$(FLASK) --app wsgi:app seed-demo

run:
	$(FLASK) --app wsgi:app run --debug

test:
	$(PYTHON) -m pytest --cov-fail-under=$(COVERAGE_TOTAL_MIN)
	$(PYTHON) -m coverage json -o $(COVERAGE_JSON)
	$(PYTHON) tools/check_coverage_thresholds.py --json-file $(COVERAGE_JSON) --min-total $(COVERAGE_TOTAL_MIN) --min-statement $(COVERAGE_STATEMENT_MIN) --min-branch $(COVERAGE_BRANCH_MIN)

test-functional:
	$(PYTHON) -m pytest tests/functional

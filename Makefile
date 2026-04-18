PYTHON := .venv/bin/python
PIP := .venv/bin/pip
FLASK := .venv/bin/flask
ALEMBIC := .venv/bin/alembic

.PHONY: install init-db db-current db-history seed-demo run

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

PYTHON := .venv/bin/python
PIP := .venv/bin/pip
FLASK := .venv/bin/flask

.PHONY: install init-db seed-demo run

install:
	$(PIP) install -e .[dev]

init-db:
	$(FLASK) --app wsgi:app init-db

seed-demo:
	$(FLASK) --app wsgi:app seed-demo

run:
	$(FLASK) --app wsgi:app run --debug


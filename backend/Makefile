PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MYPY ?= $(PYTHON) -m mypy

.PHONY: test lint format typecheck check migrate seed-demo-users

test:
	PYTHONPATH=src $(PYTEST) tests

lint:
	$(RUFF) check src tests

format:
	$(RUFF) format src tests

typecheck:
	PYTHONPATH=src $(MYPY) src

migrate:
	PYTHONPATH=src $(PYTHON) -m src.db.bootstrap migrate

seed-demo-users:
	PYTHONPATH=src $(PYTHON) -m src.db.bootstrap seed-demo-users

check: lint typecheck test

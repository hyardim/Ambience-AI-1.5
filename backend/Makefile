PYTHON ?= python3
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
MYPY ?= $(PYTHON) -m mypy

.PHONY: test lint format typecheck check

test:
	PYTHONPATH=src $(PYTEST) tests

lint:
	$(RUFF) check src tests

format:
	$(RUFF) format src tests

typecheck:
	PYTHONPATH=src $(MYPY) src

check: lint typecheck test

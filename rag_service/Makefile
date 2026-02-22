.PHONY: help install install-dev setup db-up db-down db-reset test lint format type-check clean run-ingest run-query

help:
	@echo "Available commands:"
	@echo "  make install       - Install production dependencies"
	@echo "  make install-dev   - Install development dependencies"
	@echo "  make setup         - Set up project (create dirs, copy .env)"
	@echo "  make db-up         - Start database"
	@echo "  make db-down       - Stop database"
	@echo "  make db-reset      - Reset database"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linter (ruff)"
	@echo "  make format        - Format code (ruff)"
	@echo "  make type-check    - Run type checker (mypy)"
	@echo "  make clean         - Clean cache and temp files"
# 	@echo "  make run-ingest    - Run ingestion pipeline"
# 	@echo "  make run-query     - Run RAG query"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	python -m nltk.downloader punkt punkt_tab
	python scripts/verify_nltk.py

setup:
	mkdir -p data/raw data/processed logs
	[ ! -f .env ] && cp .env.example .env || echo ".env already exists, skipping"
	@echo "Setup complete! Edit .env with your configuration"

db-up:
	docker-compose up -d
	@echo "Waiting for database to be ready..."
	@sleep 5
	@echo "Database is ready!"

db-down:
	docker-compose down

db-reset:
	docker-compose down -v
	docker-compose up -d
	@sleep 5

test:
	pytest

lint:
	ruff check src/ tests/ scripts/
	ruff format --check src/ tests/ scripts/
	mypy src/

format:
	ruff format src/ tests/ scripts/
	ruff check src/ tests/ scripts/ --fix

type-check:
	mypy src/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage

# run-ingest:
# 	python scripts/ingest.py

# run-query:
# 	python scripts/query.py
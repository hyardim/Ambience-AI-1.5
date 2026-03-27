# Backend

FastAPI backend for Ambience-AI-1.5.

## Prerequisites

- Python 3.11+
- PostgreSQL (or use the repo-root Docker Compose stack)

## Local setup

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Structure

- `src/app/`: app creation and FastAPI wiring
- `src/api/`: router composition and shared API dependencies
- `src/api/endpoints/`: thin route handlers grouped by feature
- `src/services/`: business logic
- `src/repositories/`: database access
- `src/schemas/`: request and response models
- `src/core/`: config, security, logging, policy
- `src/db/`: sessions, base metadata, models, bootstrap helpers
- `alembic/`: database migrations
- `tests/`: backend test suite

## Commands

Run these from `backend/` in an environment with the backend dependencies installed.

- `make lint`
- `make format`
- `make typecheck`
- `make test`
- `make migrate`
- `make seed-demo-users`
- `make check`

## App Entry Point

The backend app is exposed from `src.main:app`.

Run locally:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

# Backend

FastAPI backend for Ambience-AI-1.5.

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

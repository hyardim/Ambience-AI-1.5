# Backend

FastAPI backend for Ambience-AI-1.5.

## Structure

- `src/api/`: route handlers and dependencies
- `src/services/`: business logic
- `src/repositories/`: database access
- `src/schemas/`: request and response models
- `src/core/`: config, security, logging, policy
- `src/db/`: ORM models, sessions, bootstrap helpers
- `tests/`: backend test suite

## Commands

Run these from `backend/` in an environment with the backend dependencies installed.

- `make lint`
- `make format`
- `make typecheck`
- `make test`
- `make check`

## App Entry Point

The backend app is exposed from `src.main:app`.

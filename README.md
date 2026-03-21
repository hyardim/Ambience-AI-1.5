# Ambience-AI-1.5

Clinical decision-support system for rheumatology and neurology. The repo
contains the backend, frontend, and `rag_service` used to ingest guideline
documents, retrieve relevant passages, and generate grounded answers.

## Repo structure

```text
backend/       FastAPI backend and business workflows
frontend/      React frontend
rag_service/   RAG ingestion/retrieval/generation service
```

For the service-specific setup and file structure, see
[`rag_service/README.md`](rag_service/README.md).

## Running the stack

The repo-root compose file is the full product stack.

Before first run, create a root `.env` from the example and set real secrets:

```bash
cp .env.example .env
docker compose up --build
```

Main endpoints:

- backend: `http://localhost:8000`
- rag service: `http://localhost:8001`
- frontend: `http://localhost:3000`

## Nginx in this repo

`nginx/` contains a production reverse-proxy config used by the optional
`nginx` Docker Compose service.

What it does:

- terminates TLS on `:443` using certs mounted from `nginx/certs/`
- redirects `http` (`:80`) to `https`
- proxies frontend traffic (`/`) to the frontend container
- proxies backend API traffic (`/api/`) to the backend container
- disables buffering on `/api/` for SSE chat streaming reliability

How it is used:

- the `nginx` service is behind the Compose `production` profile
- it is not started by default during local development
- local dev usually accesses `frontend:3000` and `backend:8000` directly

Start with nginx enabled:

```bash
docker compose --profile production up --build
```

## Model paths

The project supports:

- local Ollama Med42
- cloud OpenAI-compatible Med42 endpoints
- routing between local and cloud providers
- provider fallback when one path fails

## Local Ollama setup

Use this for lower-cost local development.

```bash
ollama pull thewindmom/llama3-med42-8b
ollama serve
```

Typical `rag_service/.env` values:

- `OLLAMA_BASE_URL=http://host.docker.internal:11434` for Docker on macOS
- `OLLAMA_MODEL=thewindmom/llama3-med42-8b`

## Cloud hosting

The cloud path expects an OpenAI-compatible endpoint. Common choices:

- RunPod + vLLM
- AWS EC2 GPU + vLLM
- another hosted OpenAI-compatible inference endpoint

## Routing behavior

High level:

1. `rag_service` retrieves relevant chunks from pgvector.
2. It scores the request using routing heuristics.
3. It sends the request to local or cloud based on the route score and config.
4. If the chosen provider fails, it retries with the other provider.
5. If both fail, the request errors.

Important routing variables:

- `LLM_ROUTE_THRESHOLD`
- `FORCE_CLOUD_LLM`
- `ROUTE_REVISIONS_TO_CLOUD`

## Backend Redis cache

The backend caches read-heavy endpoints in Redis to reduce database load and improve latency.

Useful backend env vars:

- `REDIS_URL`
- `CACHE_ENABLED`
- `CACHE_CHAT_LIST_TTL`
- `CACHE_CHAT_DETAIL_TTL`
- `CACHE_PROFILE_TTL`
- `CACHE_SPECIALIST_LIST_TTL`
- `CACHE_ADMIN_STATS_TTL`
- `CACHE_ADMIN_CHAT_TTL`
- `CACHE_ADMIN_AUDIT_LOG_TTL`
- `CACHE_NOTIFICATION_TTL`
- `CACHE_KEY_PREFIX`

Cache troubleshooting:

- To disable caching temporarily, set `CACHE_ENABLED=false` and restart the backend.
- To reset only backend cache keys, run: `redis-cli KEYS "cache:*" | xargs redis-cli DEL`
- If you see stale chat data, confirm you updated the correct environment variables for the backend service.
- If Redis is not reachable, the backend will fall back to database reads and log a `cache.error` warning.

## Notes

- The cloud-hosting guide has been merged into this README.
- `rag_service/README.md` remains the detailed service setup and maintenance guide.

## Legacy Deployment Note

The old Gaudi/Habana Med42 TGI deployment helper scripts were retired.

- The former `serve/` scripts for a `tgi-med42` container are no longer part of this active stack.
- Current `rag_service` generation uses the configured local/cloud providers from `rag_service/src/config.py`.
- Default local development setup is Ollama-based (see `rag_service/README.md`).

If historical Gaudi/TGI details are needed, recover them from git history.

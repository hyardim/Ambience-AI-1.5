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
ollama serve
docker compose up -d
```

The default local stack is now prepared for first-run evaluation:

- the backend container runs its own startup preparation step on boot
- Postgres initializes the RAG schema and loads a pre-seeded `rag_chunks`
  corpus from the RAG DB migration assets on a fresh database directory
- local development does not require separate ingestion commands in the common
  case

Important note for existing local volumes:

- the pre-seeded RAG corpus is loaded only when Postgres initializes a fresh
  `postgres_data/` directory
- if you already have a local database volume, Docker will keep using it and
  will not rerun the init seed automatically
- for a truly fresh local bootstrap, stop the stack and remove `postgres_data/`
  before running `docker compose up -d`

RAG DB bootstrap assets now live together under:

- [rag_service/scripts/db/migrations/001_create_rag_chunks.sql](rag_service/scripts/db/migrations/001_create_rag_chunks.sql)
- [rag_service/scripts/db/migrations/002_indexes.sql](rag_service/scripts/db/migrations/002_indexes.sql)
- [rag_service/scripts/db/migrations/003_add_text_search_vector.sql](rag_service/scripts/db/migrations/003_add_text_search_vector.sql)
- [rag_service/scripts/db/migrations/004_seed_rag_chunks.sql.gz](rag_service/scripts/db/migrations/004_seed_rag_chunks.sql.gz)

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

Certificate behavior:

- if `nginx/certs/fullchain.pem` and `nginx/certs/privkey.pem` exist, nginx uses them
- if cert files are missing and `NGINX_GENERATE_SELF_SIGNED=true`, nginx generates a short-lived self-signed cert at startup
- for strict production TLS, set `NGINX_GENERATE_SELF_SIGNED=false` and mount real cert files

How it is used:

- the `nginx` service is behind the Compose `production` profile
- it is not started by default during local development
- local dev usually accesses `frontend:3000` and `backend:8000` directly
- the default local stack does not require nginx at all

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

## Tips for best results

These tips apply to anyone using the clinical interface.

### For GPs — creating a query

- **Include patient context.** The more detail you provide (age, sex, specialty, severity), the more targeted the generated answer will be. A query of "50F with RA on hydroxychloroquine — monitoring schedule?" will retrieve and rank more relevant passages than a bare drug name.
- **Attach relevant documents.** Patient letters, test results, or recent correspondence can be uploaded alongside the query. The RAG service incorporates these as additional context alongside the indexed guidelines, so the answer can reference patient-specific findings directly.
- **Be specific about the clinical question.** Naming the drug, condition, or procedure (rather than describing symptoms only) improves keyword and vector retrieval precision.

### For specialists — refining an AI-generated answer

- **Try the AI-revision path before editing manually.** If the generated answer is close but needs adjustments — different emphasis, a missing point, or a correction — use the "revise with feedback" option and describe exactly what needs to change. The service will regenerate the answer grounded in the same retrieved passages, with your feedback applied. This is usually faster than editing free-text and keeps citations consistent.
- **Be explicit in revision feedback.** Vague instructions like "improve this" produce little change. Specific instructions like "add that prednisolone should be tapered gradually" or "remove the section about cauda equina — it's not relevant here" work much better.
- **Write a manual response when the AI answer is fundamentally off.** If retrieval missed the relevant guideline entirely, or the clinical scenario is outside the indexed corpus, writing a manual response with your own sources is the right call. Manual responses are clearly marked in the audit trail.

### General

- **Emergency presentations** (neutropenic sepsis, cauda equina syndrome, acute cord compression) will trigger immediate-action guidance at the top of the answer regardless of how the query is phrased.
- **Regenerating vs editing** — if an answer is unsatisfactory for no obvious reason, try regenerating it (re-submit the same query) before investing time in manual edits. LLM output has natural variance and a fresh generation often resolves the issue.

## Notes

- The cloud-hosting guide has been merged into this README.
- `rag_service/README.md` remains the detailed service setup and maintenance guide.

## Legacy Deployment Note

The old Gaudi/Habana Med42 TGI deployment helper scripts were retired.

- The former `serve/` scripts for a `tgi-med42` container are no longer part of this active stack.
- Current `rag_service` generation uses the configured local/cloud providers from `rag_service/src/config.py`.
- Default local development setup is Ollama-based (see `rag_service/README.md`).

If historical Gaudi/TGI details are needed, recover them from git history.

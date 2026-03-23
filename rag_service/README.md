# RAG Service

Clinical retrieval-augmented generation service for Ambience AI 1.5. It ingests
medical documents, stores chunk embeddings in pgvector, retrieves relevant
guideline passages, and generates grounded answers with citations.

## Current structure

```text
src/
├── api/             # FastAPI app, routes, schemas, streaming, citation shaping
├── config/          # Structured settings package and shared config objects
├── generation/      # Prompt building, provider routing, local/cloud LLM clients
├── ingestion/       # Extract, clean, chunk, embed, and store documents
├── jobs/            # Retry queue logic
├── orchestration/   # Retrieve-then-generate pipeline helpers
├── retrieval/       # Vector, keyword, fusion, rerank, and citation assembly
├── utils/           # Shared DB and logging utilities
└── main.py          # Thin compatibility entrypoint / public re-export
```

## Prerequisites

- Python 3.10+
- Docker with the Compose plugin (`docker compose`)
- A running local Ollama instance if you want the default local model path

## Local setup

```bash
cd rag_service
python -m venv .venv
source .venv/bin/activate
make install-dev
make setup
```

`make setup` creates the local directories, copies `.env.example` to `.env` if
needed, and verifies the NLTK tokenizer data used by ingestion.

## Environment

The service reads settings from `.env` via the `src/config/` package.

Important groups in [`.env.example`](.env.example):

- Database: `POSTGRES_*`, optional `DATABASE_URL`
- Embeddings: `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`
- Chunking: `CHUNK_SIZE`, `CHUNK_OVERLAP`
- Logging: `LOG_LEVEL`, `LOG_FILE`
- Local model: `OLLAMA_*`, `LOCAL_LLM_*`
- Docker local model override: `DOCKER_OLLAMA_BASE_URL`
- Cloud model: `RUNPOD_*`, `LLM_*`, `CLOUD_LLM_*`
- Routing: `LLM_ROUTE_THRESHOLD`, `ROUTE_REVISIONS_TO_CLOUD`, `FORCE_CLOUD_LLM`
- Retry queue: `REDIS_URL`, `RETRY_*`
- Optional alerting webhook: `LLM_FALLBACK_ALERT_WEBHOOK_URL`, `LLM_FALLBACK_ALERT_TIMEOUT_SECONDS`

If `DATABASE_URL` is blank, the service builds it from the individual
`POSTGRES_*` settings.

## Running with Docker Compose

This folder's [`docker-compose.yml`](docker-compose.yml) is scoped to the RAG service only:

- `db_vector`
- `redis`
- `rag_service`
- `rag_worker`

Start dependencies:

```bash
make db-up
```

Start the API container:

```bash
docker compose up -d rag_service
```

Start the retry worker:

```bash
docker compose up -d rag_worker
```

Stop everything in this local RAG stack:

```bash
make db-down
```

Notes:

- The compose file mounts `src/`, `scripts/`, `configs/`, `data/`, and `logs/`
  into the container so local edits, ingestion output, and `/docs/{doc_id}`
  file serving work correctly.
- Docker containers use `DOCKER_OLLAMA_BASE_URL` so they can reach an Ollama
  instance running on the host machine without having to change the normal
  local `OLLAMA_BASE_URL=http://localhost:11434` setting used outside Docker.
- For the full product stack (`backend`, `frontend`, `rag_service`, database),
  use the repo-root [`docker-compose.yml`](../docker-compose.yml) instead.

## Running without Docker

Start only Postgres and Redis:

```bash
make db-up
```

Then run the FastAPI app directly:

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
```

Run the retry worker in another terminal:

```bash
make run-retry-worker
```

## Common commands

```bash
make install-dev
make format
make lint
make test
make type-check
make run-ingest INPUT=data/raw/neurology/NICE SOURCE=NICE
make run-retry-worker
```

`make lint` runs:

- Ruff lint
- Ruff format check
- MyPy

## Ingestion

CLI ingestion entrypoint:

```bash
python -m src.ingestion.cli ingest --input data/raw/neurology/NICE --source-name NICE
```

Or via the Makefile:

```bash
make run-ingest INPUT=data/raw/neurology/NICE SOURCE=NICE
```

The ingestion pipeline:

```text
Extract -> Clean -> Chunk -> Attach metadata -> Embed -> Store
```

## API surface

Main endpoints exposed by the FastAPI app:

- `POST /query`
- `POST /answer`
- `POST /revise`
- `POST /ingest`
- `GET /jobs/{job_id}`
- `GET /docs/{doc_id}`
- `GET /health`
- `POST /ask` (alternate lightweight route)

### Streaming

`/answer` and `/revise` support `"stream": true` and return NDJSON events:

- `chunk`
- `done`
- `error`

Example:

```bash
curl -s -N http://localhost:8001/answer \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is migraine?","specialty":"neurology","stream":true}'
```

## Retry queue

Transient generation failures can be queued and retried asynchronously through
Redis + RQ. The API returns `202 Accepted` with a `job_id`, and clients can poll
`GET /jobs/{job_id}` for progress.

## Testing and quality

```bash
make test
make lint
```

Tests mirror the `src/` structure under [`tests/`](tests/).

At the time of this cleanup pass:

- lint passes
- type checks pass
- tests pass
- coverage is at 100%

## Notes for maintainers

- The authoritative settings live in [`src/config/__init__.py`](src/config/__init__.py).
- The main app entrypoint is [`src.main:app`](src/main.py).
- [`src/api/ask_routes.py`](src/api/ask_routes.py) is still live because the app includes the `/ask` router.

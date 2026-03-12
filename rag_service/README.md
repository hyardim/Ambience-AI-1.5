# RAG Service — Ambience AI 1.5

A production-ready Retrieval-Augmented Generation (RAG) service for medical guidelines. Ingests PDFs from sources like NICE and BSR, chunks and embeds them, stores vectors in pgvector, and serves semantically relevant context for AI-generated clinical responses with proper citations.

---

## Architecture

```
src/
├── ingestion/      # PDF extraction, chunking, embedding, storage
├── retrieval/      # Vector similarity search, context ranking
├── generation/     # LLM integration, response generation, citations
└── utils/          # Shared database and logging utilities
```

The pipeline flows in one direction:

```
PDF → Extract → Clean → Chunk → Embed → Store → Retrieve → Generate
```

---

## Tech Stack

| Component       | Technology                          |
|-----------------|-------------------------------------|
| Vector Database | PostgreSQL + pgvector (HNSW index)  |
| Embeddings      | sentence-transformers (MiniLM-L6)   |
| ORM             | SQLAlchemy                          |
| Raw DB queries  | psycopg2 (vector search)            |
| Config          | pydantic-settings                   |
| PDF Extraction  | PyMuPDF                             |
| Chunking        | langchain-text-splitters            |

---

## Getting Started

### Prerequisites
- Python 3.10+ (3.12 recommended on macOS to avoid PyMuPDF build issues)
- Docker + Docker Compose

### Setup

```bash
# 1. Clone the repo and navigate to rag_service
cd rag_service

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
make install-dev

# 4. Set up environment and directories
make setup
# Edit .env with your configuration

# 5. Start the database
make db-up
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=admin
POSTGRES_PASSWORD=your_password
POSTGRES_DB=ambience_knowledge

# Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384

# Chunking
CHUNK_SIZE=450
CHUNK_OVERLAP=100

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/rag.log

# Retry queue
REDIS_URL=redis://localhost:6379/0
RETRY_ENABLED=true
RETRY_MAX_ATTEMPTS=3
RETRY_BACKOFF_SECONDS=10
RETRY_BACKOFF_MULTIPLIER=2
RETRY_JOB_TTL_SECONDS=86400
```

---

## Retry Queue (Redis + Worker)

When `/answer` or `/revise` fails due to transient provider/network/timeouts, the
request is queued and retried asynchronously. The API returns `202` with a job id
that can be polled via `/jobs/{job_id}`.

### Run Redis locally

```bash
docker run --name ambience-redis -p 6379:6379 -d redis:7-alpine
```

Or via Docker Compose:

```bash
docker compose up -d redis
```

### Start the retry worker

```bash
python scripts/run_retry_worker.py
```

Or via Docker Compose:

```bash
docker compose up -d rag_worker
```

### Example request flow

```text
POST /answer -> 202 { job_id: "...", status: "queued" }
GET  /jobs/{job_id} -> { status: "retrying", attempt_count: 1 }
GET  /jobs/{job_id} -> { status: "succeeded", response: { ... } }
```

Validation errors and 4xx provider responses are not retried and return
immediate failures.

---

## Development

### Citation links (what to expect)

- The RAG service now caps citations to the top 3 retrieved chunks and tells the model to only cite passages it actually used, so you should not see unused citation numbers.
- Source links in the UI point to `http://localhost:8001/docs/{doc_id}#page={page}` and open inline in the browser PDF viewer (no forced download) as long as `rag_service` is running.
- To refresh citations after code changes, re-run ingestion so chunk metadata (including `source_path`) is stored in Postgres, then retest a chat message.

### Common Commands

```bash
make install-dev    # Install all dependencies including dev tools
make db-up          # Start postgres database
make db-down        # Stop database
make db-reset       # Wipe and restart database
make format         # Auto-fix formatting and imports (ruff)
make lint           # Run ruff + mypy
make test           # Run tests with coverage report
make run-ingest     # Run ingestion pipeline
make run-query      # Run RAG query
```

### Before Every Commit

```bash
make format
make lint
make test
```

All three must pass before pushing.

---

## Database Schema

### `documents`
One row per ingested PDF.

| Column        | Type      | Description                        |
|--------------|-----------|------------------------------------|
| id           | SERIAL    | Primary key                        |
| filename     | TEXT      | Original PDF filename              |
| specialty    | TEXT      | Medical specialty (e.g. neurology) |
| publisher    | TEXT      | Source (e.g. NICE, BSR)            |
| file_path    | TEXT      | Path to source PDF                 |
| total_pages  | INTEGER   | Page count                         |
| total_chunks | INTEGER   | Number of chunks generated         |
| ingested_at  | TIMESTAMP | Ingestion timestamp                |
| metadata     | JSONB     | Additional document metadata       |

### `chunks`
One row per text chunk with its embedding.

| Column        | Type        | Description                      |
|--------------|-------------|----------------------------------|
| id           | SERIAL      | Primary key                      |
| document_id  | INTEGER     | Foreign key to documents         |
| chunk_index  | INTEGER     | Position within document         |
| content      | TEXT        | Chunk text                       |
| embedding    | vector(384) | Sentence embedding               |
| page_number  | INTEGER     | Source page                      |
| section_title| TEXT        | Section heading                  |
| chunk_type   | TEXT        | Type of content                  |
| token_count  | INTEGER     | Token count                      |
| metadata     | JSONB       | Additional chunk metadata        |

---

## Data Directory Structure

```
data/
├── raw/
│   ├── rheumatology/
│   │   ├── NICE/
│   │   └── BSR/
│   └── neurology/
│       ├── NICE/
│       └── BSR/
└── processed/
```

---

## Testing

```bash
make test
```

Tests are in `tests/` mirroring the `src/` structure. Coverage is enforced at 90% minimum in CI.

```
tests/
├── ingestion/
├── retrieval/
└── generation/
```

---

## CI/CD

GitHub Actions runs on every PR and push to `main`:

1. Ruff lint
2. Ruff format check
3. MyPy type check
4. Pytest with coverage

PRs cannot be merged unless all checks pass.

---

## Project Structure

```
rag_service/
├── .github/workflows/ci.yml   # CI pipeline
├── .vscode/settings.json      # VS Code config
├── data/                      # Raw and processed documents
├── logs/                      # Runtime logs
├── scripts/
│   └── init_db.sql            # Database schema
├── src/
│   ├── config.py              # Pydantic settings
│   ├── generation/            # LLM + response generation
│   ├── ingestion/             # PDF pipeline
│   ├── retrieval/             # Vector search
│   └── utils/
│       ├── db.py              # Database manager
│       └── logger.py          # Logging setup
├── tests/                     # Test suite
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── pyproject.toml
```
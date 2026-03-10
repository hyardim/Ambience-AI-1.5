# Ambience-AI-1.5

**A Specialized Clinical Decision Support System for Rheumatology & Neurology.**

## 📖 Project Overview

This project implements a **Microservices-based Retrieval-Augmented Generation (RAG)** system designed to assist clinicians with accurate, guideline-backed answers. Unlike generic chatbots, this system functions as a "hyper-tuned" medical specialist. It decouples application logic from high-performance inference to ensure scalability and clinical safety.

The core logic is orchestrated by **LangChain**, which retrieves context from a curated **Vector Database (Digital Library)** of UK clinical guidelines. This context is processed by **MED-42** (via Ollama), a specialized Large Language Model (LLM) fine-tuned for medical reasoning, running locally.

## 🏗️ Technical Architecture

The system follows a decoupled microservices topology:

* **Orchestrator (LangChain):** Acts as the central controller (CPU-bound). It handles prompt engineering, tool selection, and conversation memory.
* **Digital Library (Vector DB):** Stores high-dimensional embeddings of Rheumatology and Neurology clinical guidelines for semantic retrieval.
* **LLM Endpoint (Ollama + Med42):** Local inference served by Ollama running the **MED-42** model.
* **Safety Layer:** Implements automated "Red Teaming" and strict output validation to minimize hallucination and ensure clinical disclaimer compliance.

## ⚡ Hardware & Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Hardware** | **Local CPU/GPU** | Runs Ollama for Med42 inference. |
| **LLM Runtime** | **Ollama** | Serves the Med42 model locally. |
| **Model** | **MED-42** | "Hyper-tuned" Llama-based model for clinical reasoning. |
| **Framework** | **LangChain** | Application orchestration and RAG logic. |

## 🎯 Key Features

* **Domain Specific:** Hyper-tuned specifically for **Rheumatology** and **Neurology** queries.
* **Grounded Generation:** Every response is grounded in retrieved text chunks from verified PDF guidelines (RAG).
* **Clinical Safety:** Includes adversarial defense mechanisms and mandatory disclaimer injection.

## Running with RunPod (2x A100 PCIe + vLLM)

### RunPod pod settings (required)

Create a new RunPod pod with:

- **GPU**: `2x A100 PCIe`
- **Template**: latest **vLLM** template
- **Container disk / volume disk**: `400 GB`
- **Open port**: `8000`

Use this model + launch arguments in the vLLM command field:

`m42-health/Llama3-Med42-70B --host 0.0.0.0 --port 8000 --tensor-parallel-size 2 --dtype bfloat16 --gpu-memory-utilization 0.92 --max-model-len 4096 --disable-custom-all-reduce --enforce-eager`

Notes:

- `3072` also works for `--max-model-len` (safer VRAM).
- If your pod remains stable, you can increase to `4096` or `6144`.

### Required environment variables in RunPod

Set these in the pod environment variables:

- `HF_TOKEN=<your_huggingface_token>`
- `JUPYTER_PASSWORD=<your_strong_password>`

How to get the Hugging Face token:

1) Sign in to Hugging Face.
2) Go to **Settings → Access Tokens**.
3) Create a token with at least **Read** scope.
4) Copy it and set it as `HF_TOKEN` in RunPod.

`JUPYTER_PASSWORD` is user-defined (create your own strong password and store it in your password manager).

### Wire the pod endpoint/token into this project

The code reads `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`.

In `rag_service/.env` set:

- `LLM_BASE_URL=https://<YOUR_POD_ID>-8000.proxy.runpod.net/v1`
- `LLM_MODEL=m42-health/Llama3-Med42-70B`
- `LLM_API_KEY=<YOUR_RUNPOD_POD_TOKEN>`

Get `<YOUR_RUNPOD_POD_TOKEN>` from **RunPod Dashboard → Settings → API Keys** (create one if needed).

If you run from the root `docker-compose.yml`, also set the compose variables (for consistency with the compose env wiring):

- `CLOUD_LLM_BASE_URL=https://<YOUR_POD_ID>-8000.proxy.runpod.net/v1`
- `CLOUD_LLM_MODEL=m42-health/Llama3-Med42-70B`
- `CLOUD_LLM_API_KEY=<YOUR_RUNPOD_POD_TOKEN>`

Then start the stack:

- `docker compose up --build`

Verify RAG service connectivity:

- `curl http://localhost:8001/health`
- `curl -X POST http://localhost:8001/answer -H "Content-Type: application/json" -d '{"query":"what is rheumatoid arthritis?","top_k":3}'`

## Running locally with Ollama (keep this for dev)

Use this mode when you want lower cost local development.

1) Install and run Ollama on host:
	- `brew install ollama` (or official installer)
	- `ollama pull thewindmom/llama3-med42-8b`
	- `ollama serve`

2) Point `rag_service/.env` to local model:
	- `LLM_BASE_URL=http://host.docker.internal:11434/v1`
	- `LLM_MODEL=thewindmom/llama3-med42-8b`
	- `LLM_API_KEY=ollama`

3) Start stack and test:
	- `docker compose up --build`
	- `curl http://localhost:8001/health`
	- `curl -X POST http://localhost:8001/answer -H "Content-Type: application/json" -d '{"query":"what is rheumatoid arthritis?","top_k":3}'`

## Model selection algorithm (current behavior)

The runtime now uses **query-aware heuristic routing** with automatic fallback:

- Router implementation is in `rag_service/src/generation/router.py` (`select_generation_provider`).
- Route score is built from three components:
	- **Complexity score**: query length, sentence count, and reasoning terms (e.g. `differential`, `compare`, `management`, `contraindications`).
	- **Risk score**: explicit risk/urgency terms in query and optional request `severity` (`urgent` / `emergency`).
	- **Ambiguity score**: retrieval confidence and separability (top score and top-2 score gap).
- Final provider decision:
	- if `score >= LLM_ROUTE_THRESHOLD` → **cloud-first** (`CLOUD_LLM_*`),
	- else → **local-first** (`LOCAL_LLM_*`).
- Revision override:
	- when `ROUTE_REVISIONS_TO_CLOUD=true`, `/revise` is forced cloud-first.

Fallback behavior (both directions):

- Cloud-first request: if cloud fails, automatically retries locally.
- Local-first request: if local fails, automatically retries in cloud.
- If both fail, API returns an error.

Operational notes:

- Health endpoint now exposes routing context (`local_model`, `cloud_model`, `route_threshold`) at `GET /health`.
- Routing decisions are logged in service logs with provider, score, threshold, and reason tags.

### How requests flow

- Frontend (or API) sends `POST /chats/{chat_id}/message` to the backend.
- Backend forwards the user message to RAG service `/answer`, saves user and assistant messages, and appends source citations if returned.
- RAG service embeds the query, retrieves chunks from pgvector, runs the heuristic router, then calls cloud/local in routed order with automatic fallback.

### Troubleshooting

- If `/answer` times out: confirm local and cloud endpoints are both correct in env (`LOCAL_LLM_*`, `CLOUD_LLM_*`) and that the routed provider is reachable.
- If citations are empty: ensure documents are ingested into pgvector; check RAG logs for ingestion errors.
- If pgvector is missing: the RAG service will attempt to create the extension and schema on startup; check container logs for errors.

### Local testing prerequisites (dev deps)

- Before running pytest locally, install the dev extras for the RAG service so tests have all heavy dependencies (PyMuPDF, sentence-transformers, tiktoken, etc.):
	- `cd rag_service && pip install -e .[dev]`
	- `python -m nltk.downloader punkt punkt_tab` (needed for sentence splitting)
- Backend tests only need the standard backend requirements (`pip install -r backend/requirements.txt`).
- CI should do the same (use the `dev` extra) if you want the full rag_service test suite to run.

## Quick start (docker compose)

- Bring everything up: `docker compose up --build` (services: backend at 8000, frontend at 3000, rag_service at 8001, pgvector at 5432).
- Log in (seed user): `gp@example.com` / `password123` via frontend or `POST /auth/login`.
- Send a chat message: `POST /chats/{id}/message` with Bearer token; backend forwards to rag_service `/answer`.
- View sources: UI “Sources” links hit `http://localhost:8001/docs/{doc_id}#page={page}` and open inline.

## Ingestion quick reference

- PDFs live in `rag_service/data/raw/{specialty}/{publisher}/...`.
- Re-ingest after adding or updating PDFs:
	- `docker compose exec rag_service python -m src.ingestion.cli ingest --input data/raw/neurology/NICE --source-name NICE --log-level INFO`
- Ingestion writes chunk metadata (including `source_path`) to Postgres so citation links work.

## Citation behavior (current)

- RAG caps citations to the top 3 retrieved chunks and instructs the model to only cite passages it used; unused citation numbers should not appear.
- Source links are served inline from `rag_service` via `/docs/{doc_id}`, so clicking opens the PDF in-browser.

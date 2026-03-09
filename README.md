# Ambience-AI-1.5

**A Specialized Clinical Decision Support System for Rheumatology & Neurology.**

## 📖 Project Overview

This project implements a **Microservices-based Retrieval-Augmented Generation (RAG)** system designed to assist clinicians with accurate, guideline-backed answers. Unlike generic chatbots, this system functions as a "hyper-tuned" medical specialist. It decouples application logic from high-performance inference to ensure scalability and clinical safety.

The core logic is orchestrated by **LangChain**, which retrieves context from a curated **Vector Database (Digital Library)** of UK clinical guidelines. This context is processed by **MED-42** (via Ollama), a specialized Large Language Model (LLM) fine-tuned for medical reasoning, running locally.

The system now also supports a **cloud-hosted RunPod Med42 70B endpoint** and can route between local and cloud providers with automatic fallback.

## 🏗️ Technical Architecture

The system follows a decoupled microservices topology:

* **Orchestrator (LangChain):** Acts as the central controller (CPU-bound). It handles prompt engineering, tool selection, and conversation memory.
* **Digital Library (Vector DB):** Stores high-dimensional embeddings of Rheumatology and Neurology clinical guidelines for semantic retrieval.
* **LLM Endpoints:** Local inference via Ollama and cloud inference via RunPod/vLLM for larger Med42 models.
* **Safety Layer:** Implements automated "Red Teaming" and strict output validation to minimize hallucination and ensure clinical disclaimer compliance.

## ⚡ Hardware & Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Hardware** | **Local CPU/GPU** | Runs Ollama for Med42 inference. |
| **Cloud Inference** | **RunPod + vLLM** | Hosts the Med42 70B model behind an OpenAI-compatible API. |
| **LLM Runtime** | **Ollama** | Serves the Med42 model locally. |
| **Model** | **MED-42** | "Hyper-tuned" Llama-based model for clinical reasoning. |
| **Framework** | **LangChain** | Application orchestration and RAG logic. |

## 🎯 Key Features

* **Domain Specific:** Hyper-tuned specifically for **Rheumatology** and **Neurology** queries.
* **Grounded Generation:** Every response is grounded in retrieved text chunks from verified PDF guidelines (RAG).
* **Hybrid Routing:** Requests can be sent to the local or cloud model based on routing heuristics.
* **Provider Fallback:** If the chosen provider fails, the service automatically retries with the other one.
* **Clinical Safety:** Includes adversarial defense mechanisms and mandatory disclaimer injection.

## Running with Ollama (local)

### Environment

- Python: 3.10+ (tested on 3.12). On macOS ARM, Python 3.12 avoids PyMuPDF build issues; use a 3.12 venv if pip install fails on earlier versions.

Set these variables (docker-compose already wires them through):

- `OLLAMA_BASE_URL`: `http://host.docker.internal:11434` on macOS when Ollama runs on the host.
- `OLLAMA_MODEL`: `thewindmom/llama3-med42-8b` (pull locally with `ollama pull thewindmom/llama3-med42-8b`).
- `OLLAMA_MAX_TOKENS`: optional cap for the answer endpoint (defaults in code if unset).
- `LOCAL_LLM_BASE_URL` / `LOCAL_LLM_MODEL`: optional explicit local model override for routing.
- `RUNPOD_POD_ID` / `RUNPOD_PORT` / `RUNPOD_API_KEY`: pod-specific variables used to build the RunPod URL and auth automatically.
- `CLOUD_LLM_BASE_URL` / `CLOUD_LLM_API_KEY`: optional direct overrides; leave blank to auto-build from `RUNPOD_*`.
- `CLOUD_LLM_MODEL`: RunPod OpenAI-compatible endpoint model name for the cloud 70B path.
- `LLM_ROUTE_THRESHOLD`: route to the cloud model when the request complexity score is above this threshold (default `0.65`).
- `FORCE_CLOUD_LLM`: optional override; set `true` only if you want all requests to prefer cloud before fallback.

## RunPod pod setup guide

When you create or switch to a new RunPod pod, update only the pod-related values.

### 1) Start the pod

- Start a RunPod pod that exposes a vLLM/OpenAI-compatible API on port `8000`.
- Wait until the pod is fully running before testing the proxy URL.

### 2) Use a vLLM start command

Example pattern:

- `m42-health/Llama3-Med42-70B --host 0.0.0.0 --port 8000 --tensor-parallel-size 2 --dtype bfloat16 --gpu-memory-utilization 0.92 --max-model-len 3072 --disable-custom-all-reduce --enforce-eager`

The important part for this repo is that the pod serves the OpenAI-style endpoint at:

- `/v1/chat/completions`

### 3) Set the pod variables in your local env

In [rag_service/.env.example](rag_service/.env.example), copy these values into your local env file and replace them with the new pod values:

- `RUNPOD_POD_ID=YOUR_RUNPOD_POD_ID`
- `RUNPOD_PORT=8000`
- `RUNPOD_API_KEY=sk-$RUNPOD_POD_ID`

If your pod uses a different API key value, set `RUNPOD_API_KEY` to that exact value.

### 4) Recreate the RAG container

Environment changes require recreation, not only restart:

- `docker compose up -d --force-recreate rag_service`

### 5) Test the pod directly

Before testing the app, verify the pod itself:

- `curl -i https://<RUNPOD_POD_ID>-<RUNPOD_PORT>.proxy.runpod.net/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer <RUNPOD_API_KEY>" -d '{"model":"m42-health/Llama3-Med42-70B","messages":[{"role":"user","content":"Say hello"}],"max_tokens":20}'`

If this direct call fails, the app fallback will also fail.

## High-level routing overview

The routing logic now works like this:

1. The RAG service retrieves the most relevant chunks from pgvector.
2. It scores the request using simple heuristics such as:
	- query length and complexity
	- risk terms and urgency
	- ambiguity of retrieval results
	- revision workflow signals
3. If the score is above `LLM_ROUTE_THRESHOLD`, the request is sent to the cloud model.
4. Otherwise, it is sent to the local model first.
5. If the chosen provider fails:
	- local → retry cloud
	- cloud → retry local
6. If both providers fail, the API returns an error describing both failures.

In short:

- **Normal mode:** score-based routing
- **Failure mode:** automatic cross-provider fallback
- **Hard failure:** both providers unavailable

### Steps

1) Install and start Ollama on the host, then pull the model:
	- `brew install ollama` (or follow Ollama docs)
	- `ollama pull thewindmom/llama3-med42-8b`
	- `ollama serve` (if not already running)

2) Start the stack (brings up pgvector, backend, and RAG service):
	- `docker compose up --build`

3) Verify RAG service connectivity:
	- `curl http://localhost:8001/health`
	- `curl -X POST http://localhost:8001/answer -H "Content-Type: application/json" -d '{"query":"what is rheumatoid arthritis?","top_k":3}'`

### How requests flow

- Frontend (or API) sends `POST /chats/{chat_id}/message` to the backend.
- Backend forwards the user message to RAG service `/answer`, saves user and assistant messages, and appends source citations if returned.
- RAG service embeds the query, retrieves chunks from pgvector, builds a grounded prompt, scores the request complexity, and sends simpler requests to the local model while routing harder or revision-style requests to the configured cloud model.
- If the selected provider fails, the RAG service automatically retries with the other provider before returning an error.

### Troubleshooting

- If `/answer` times out: confirm `ollama serve` is running and reachable from containers via `host.docker.internal`.
- If cloud fallback fails: test the RunPod proxy URL directly first. If the direct `curl` fails, the issue is on the pod side rather than in the repo.
- If you changed pods and the old URL still seems active: recreate the RAG container with `docker compose up -d --force-recreate rag_service`.
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

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

## Running with RunPod (2x A100 PCIe + vLLM)

### RunPod pod settings (required)

Create a new RunPod pod with:

- **GPU**: `2x A100 PCIe`
- **Template**: latest **vLLM** template
- **Container disk / volume disk**: `400 GB`
- **Open port**: `8000`

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

## Backend Redis cache

The backend caches read-heavy endpoints in Redis to reduce database load and improve latency.

Cached data:

- Chat list responses (per user, page, status, specialty)
- Chat detail payloads (messages + files)
- Admin user profile lookups

Cache invalidation happens on chat creation/updates/deletes, message sends, file uploads,
specialist reviews, and user profile/password updates.

Environment variables (backend):

- `REDIS_URL` (default: `redis://redis:6379/0`)
- `CACHE_ENABLED` (default: `true`)
- `CACHE_CHAT_LIST_TTL` (seconds, default: `30`)
- `CACHE_CHAT_DETAIL_TTL` (seconds, default: `60`)
- `CACHE_PROFILE_TTL` (seconds, default: `300`)
- `CACHE_KEY_PREFIX` (default: `cache`)

Cache troubleshooting:

- To disable caching temporarily, set `CACHE_ENABLED=false` and restart the backend.
- To reset only backend cache keys, run: `redis-cli KEYS "cache:*" | xargs redis-cli DEL`
- If you see stale chat data, confirm you updated the correct environment variables for the backend service.
- If Redis is not reachable, the backend will fall back to database reads and log a `cache.error` warning.
- You can point the backend to a local Redis by setting `REDIS_URL=redis://localhost:6379/0`.

Cache key format:

- Chat list keys: `cache:user:{user_id}:chats:{status}:{specialty}:{page}:{page_size}`
- Chat detail keys: `cache:user:{user_id}:chat:{chat_id}`
- Profile keys: `cache:user:{user_id}:profile`
- Chat detail invalidation uses a wildcard pattern: `cache:user:*:chat:{chat_id}`
- Chat list invalidation uses a per-user pattern: `cache:user:{user_id}:chats:*`

Examples:

- `cache:user:12:chats:open:neuro:0:50`
- `cache:user:12:chat:410`
- `cache:user:12:profile`

Notes:

- `CACHE_KEY_PREFIX` replaces the leading `cache` segment.
- Keys are scoped per user to avoid cross-tenant leakage.

Cache FAQ:

- Q: Do I need Redis running to use the backend?
- A: No. If Redis is down, the backend will log a warning and read from the database directly.

- Q: Why am I still seeing old data?
- A: Check that your backend container picked up the latest env values and that the cache keys were invalidated.

- Q: How can I wipe only chat caches?
- A: Use a pattern delete, e.g. `redis-cli KEYS "cache:user:*:chats:*" | xargs redis-cli DEL`.

- Q: Can I tune how long chat details are cached?
- A: Yes. Set `CACHE_CHAT_DETAIL_TTL` in seconds and restart the backend.

- Q: What about large payloads?
- A: The cache stores JSON payloads; keep payload sizes reasonable by tuning list page sizes.

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
- RAG service embeds the query, retrieves chunks from pgvector, builds a grounded prompt, scores the request complexity, and sends simpler requests to the local model while routing harder or revision-style requests to the configured cloud model.
- If the selected provider fails, the RAG service automatically retries with the other provider before returning an error.

### Troubleshooting

- If `/answer` times out: confirm local and cloud endpoints are both correct in env (`LOCAL_LLM_*`, `CLOUD_LLM_*`) and that the routed provider is reachable.
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

## Auth email verification configuration

The backend now supports single-use email verification links for newly registered users.

- `NEW_USERS_REQUIRE_EMAIL_VERIFICATION`: when `true` (recommended), new registrations must verify email before login.
- `ALLOW_LEGACY_UNVERIFIED_LOGIN`: emergency compatibility flag for legacy rollouts; keep `false` in normal operation.
- `EMAIL_VERIFICATION_TOKEN_TTL_MINUTES`: verification token lifetime.
- `EMAIL_VERIFICATION_TOKEN_PEPPER`: secret pepper used when hashing verification tokens.
- `RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS`: resend throttle window.
- `RESEND_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS`: max resend attempts per window.
- `EMAIL_VERIFICATION_EMAIL_LOG_ONLY`: when `true`, verification emails are logged instead of sent.

SMTP settings shared by password reset and verification:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_USE_TLS`

Frontend verification routes:

- `/verify-email?token=...` to confirm verification.
- `/resend-verification` to request a fresh verification link.

Rollout note:

- Existing users are defaulted to `email_verified=true` during startup schema migration so current accounts are not locked out.

## Password reset (secure email-link flow)

The password reset flow now uses a standard, token-based design:

- `POST /auth/forgot-password` accepts only `email` and always returns a generic success message.
- `POST /auth/reset-password/confirm` accepts `token` and `new_password`.
- Reset tokens are single-use, expire automatically, and only hashed token values are stored in the database.
- Invalid, expired, or already-used tokens return a safe error (`Invalid or expired reset token`).

### Auth API contract updates

- Added: `POST /auth/forgot-password`
	- Request: `{ "email": "user@example.com" }`
	- Response: generic success message (same for existing/non-existing emails)
- Added: `POST /auth/reset-password/confirm`
	- Request: `{ "token": "...", "new_password": "..." }`
	- Response: success message on completion
- Removed insecure behavior: direct reset using `{ email, new_password }` in one call

### New backend environment variables

Set these for backend auth email/reset behavior:

- `FRONTEND_BASE_URL` (example: `http://localhost:3000`)
- `PASSWORD_RESET_TOKEN_TTL_MINUTES` (default: `30`)
- `PASSWORD_RESET_TOKEN_PEPPER` (optional, defaults to app `SECRET_KEY`)
- `FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS` (default: `900`)
- `FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS` (default: `5`)
- `SMTP_HOST`
- `SMTP_PORT` (default: `587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `SMTP_USE_TLS` (`true`/`false`, default: `true`)
- `PASSWORD_RESET_EMAIL_LOG_ONLY` (`true`/`false`, default: `true`)

### Local development notes (no real SMTP)

- Keep `PASSWORD_RESET_EMAIL_LOG_ONLY=true` to avoid sending real emails.
- In this mode, reset links are logged by the backend email service.
- Frontend uses:
	- `/forgot-password` page for email submission
	- `/reset-password?token=...` page for password confirmation

### Manual end-to-end check

1. Open the login page and select `Forgot your password?`.
2. Submit a known test email.
3. Copy the logged reset link token (or capture it in local/dev tooling).
4. Open `/reset-password?token=...`.
5. Submit a strong new password and verify login works with the new password.
6. Reuse the same token and confirm it fails with a safe invalid/expired message.

## Ingestion quick reference

- PDFs live in `rag_service/data/raw/{specialty}/{publisher}/...`.
- Re-ingest after adding or updating PDFs:
	- `docker compose exec rag_service python -m src.ingestion.cli ingest --input data/raw/neurology/NICE --source-name NICE --log-level INFO`
- Ingestion writes chunk metadata (including `source_path`) to Postgres so citation links work.

## Citation behavior (current)

- RAG caps citations to the top 3 retrieved chunks and instructs the model to only cite passages it used; unused citation numbers should not appear.
- Source links are served inline from `rag_service` via `/docs/{doc_id}`, so clicking opens the PDF in-browser.

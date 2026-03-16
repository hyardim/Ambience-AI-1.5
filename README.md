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
[`rag_service/README.md`](/Users/Kavin2/Desktop/Ambience-AI-1.5/rag_service/README.md).

## Running the stack

The repo-root compose file is the full product stack.

```bash
docker compose up --build
```

Main endpoints:

- backend: `http://localhost:8000`
- rag service: `http://localhost:8001`
- frontend: `http://localhost:5173`

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

### RunPod / vLLM

Recommended pod shape:

- GPU: `2x A100 PCIe`
- open port: `8000`
- enough disk for weights and cache

Example vLLM launch pattern:

```bash
m42-health/Llama3-Med42-70B --host 0.0.0.0 --port 8000 --tensor-parallel-size 2 --dtype bfloat16 --gpu-memory-utilization 0.92 --max-model-len 4096 --disable-custom-all-reduce --enforce-eager
```

Expected API path:

- `/v1/chat/completions`

Useful env vars:

- `RUNPOD_POD_ID`
- `RUNPOD_PORT=8000`
- `RUNPOD_API_KEY`
- optional direct overrides:
  - `CLOUD_LLM_BASE_URL`
  - `CLOUD_LLM_API_KEY`
  - `CLOUD_LLM_MODEL`

After env changes:

```bash
docker compose up -d --force-recreate rag_service
```

Direct pod smoke test:

```bash
curl -i https://<RUNPOD_POD_ID>-<RUNPOD_PORT>.proxy.runpod.net/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <RUNPOD_API_KEY>" \
  -d '{"model":"m42-health/Llama3-Med42-70B","messages":[{"role":"user","content":"Say hello"}],"max_tokens":20}'
```

### AWS / self-hosted vLLM

Typical shape:

1. GPU instance
2. vLLM server
3. restricted HTTPS or internal load balancer
4. backend / rag service allowed to call inference
5. logging and monitoring

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

Cached data:

- chat list responses
- chat detail payloads
- admin user profile lookups

Useful backend env vars:

- `REDIS_URL`
- `CACHE_ENABLED`
- `CACHE_CHAT_LIST_TTL`
- `CACHE_CHAT_DETAIL_TTL`
- `CACHE_PROFILE_TTL`
- `CACHE_KEY_PREFIX`

## Notes

- The cloud-hosting guide has been merged into this README.
- `rag_service/README.md` remains the detailed service setup and maintenance guide.

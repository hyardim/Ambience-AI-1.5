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

## Running with Ollama (local)

### Environment

- Python: 3.10+ (tested on 3.12). On macOS ARM, Python 3.12 avoids PyMuPDF build issues; use a 3.12 venv if pip install fails on earlier versions.

Set these variables (docker-compose already wires them through):

- `OLLAMA_BASE_URL`: `http://host.docker.internal:11434` on macOS when Ollama runs on the host.
- `OLLAMA_MODEL`: `thewindmom/llama3-med42-8b` (pull locally with `ollama pull thewindmom/llama3-med42-8b`).
- `OLLAMA_MAX_TOKENS`: optional cap for the answer endpoint (defaults in code if unset).

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
- RAG service embeds the query, retrieves chunks from pgvector, builds a grounded prompt, and calls Ollama at `OLLAMA_BASE_URL` with the selected `OLLAMA_MODEL`.

### Troubleshooting

- If `/answer` times out: confirm `ollama serve` is running and reachable from containers via `host.docker.internal`.
- If citations are empty: ensure documents are ingested into pgvector; check RAG logs for ingestion errors.
- If pgvector is missing: the RAG service will attempt to create the extension and schema on startup; check container logs for errors.

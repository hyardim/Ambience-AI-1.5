# Ambience-AI-1.5

Ambience AI 1.5 is a multi-role clinical decision-support platform with three core services:

- `frontend/` React + TypeScript UI for GP, Specialist, and Admin users
- `backend/` FastAPI application for auth, chat workflows, reviews, audit, notifications
- `rag_service/` retrieval-augmented generation (RAG) service for grounded clinical responses

## Repository structure

```text
backend/       FastAPI backend and business workflows
frontend/      React frontend
rag_service/   RAG ingestion/retrieval/generation service
nginx/         Optional TLS reverse proxy (production profile)
```

## Role workflows (implemented)

### GP workflow

1. Register/login and access the GP portal.
2. Create a consultation with required patient metadata:
   - title, specialty, urgency, patient age, patient sex, clinical question
3. Optionally upload supporting files.
4. Send/continue messages in consultation detail:
   - AI responses stream via SSE and include citations when available
5. Track consultations across statuses:
   - `open/submitted` -> `assigned/reviewing` -> `approved/rejected`
6. Archive consultations from the GP list when no longer needed.

### Specialist workflow

1. Open Specialist queue (`submitted` consultations; specialty-aware filtering).
2. Assign a consultation to self.
3. Review at message-level and consultation-level using actions such as:
   - approve
   - request changes (triggers RAG revise path)
   - edit response
   - replace with manual response
   - send specialist comment
   - unassign
4. Monitor revisions and live updates while AI regeneration is running.
5. Close by approving/send or rejection path, with GP notifications emitted.

### Admin workflow

1. Dashboard:
   - AI response volume
   - RAG-grounded ratio
   - consultation status/specialty distribution
   - daily trend charts and recent RAG logs
2. User management:
   - filter, edit, and deactivate users
3. Chat management:
   - inspect chat/message detail, update metadata/status, delete chats
4. Audit logs:
   - filter by category/action/user/date/search
5. Guideline ingestion:
   - upload PDF guideline sources to RAG service
6. RAG pipeline status:
   - service health, indexed docs, ingestion job counts

## Effective usage guide for clinicians

### GP playbook (recommended)

1. Start with a specific consultation title and a single clear clinical question.
2. Always provide core patient context:
   - age
   - sex
   - specialty
   - urgency
3. Add concise clinical notes with only relevant history, current meds, and key findings.
4. Upload supporting files only when they materially affect the question.
5. Review AI output with citations before acting.
6. If response quality is weak, add missing context and ask a narrower follow-up question.
7. Track consultation state and act accordingly:
   - `open`: draft/new consultation state
   - `submitted`: sent for specialist workflow
   - `assigned`: specialist has claimed it
   - `reviewing`: specialist is iterating or revising response
   - `approved`: specialist-approved response ready for GP use
   - `rejected`: response rejected and requires further action
   - `archived`: removed from GP list view

### Specialist playbook (recommended)

1. Work queue first:
   - claim consultations from `submitted` queue
   - prioritize by urgency and clinical risk
2. Review full context before decision:
   - patient details
   - GP messages
   - AI draft and citations
3. Use the right action for the situation:
   - `approve`: response is clinically acceptable as-is
   - `request_changes`: ask AI to regenerate with specialist feedback
   - `edit_response`: refine the AI text directly
   - `manual_response`: replace AI answer with specialist-authored response
   - `send_comment`: request clarification or provide specialist guidance
   - `unassign`: return case to queue if unable to continue
4. Close consultation only when response quality and safety are acceptable.
5. Ensure feedback is explicit when requesting changes to improve revision quality.

### Safety and limitations (all clinical users)

- The system is decision support, not an autonomous decision-maker.
- Responses are only as good as provided context and available guideline coverage.
- Neurology and rheumatology are the primary configured specialties in current workflows.
- File uploads are size-limited and may be truncated for context processing.
- Clinical accountability remains with licensed clinicians at point of care.

## Quick start (Docker, recommended)

### Prerequisites

- Docker + Docker Compose
- Ollama running locally (for default local model path)

### Minimum measured specs (local Med42 8B, 8-bit quantized)

Model: `thewindmom/llama3-med42-8b` (`Q8_0`), download size ~7.95 GB.

Benchmark protocol used (March 27, 2026):

- Host used for measurement: Apple M4 Pro, 14 CPU cores, 24 GB RAM
- Load profile: 12 sequential `/ask` requests + 16 `/ask` requests at concurrency 4
- Result quality during run: 100% valid JSON, 100% with citations, 0 fallback responses

Measured peak usage on this setup:

- Ollama runner RSS peak: ~8.13 GiB
- Docker services peak total: ~1.53 GiB
- Combined observed service/process peak: ~9.7 GiB (excluding normal OS + browser/editor headroom)

Recommended minimum for reliable local development:

- CPU: 4 physical cores (8 threads)
- System RAM (model only): 12 GB minimum
- System RAM (full stack + model): 16 GB minimum (24 GB preferred)
- Optional GPU for faster inference: 10 GB VRAM minimum (12 GB+ recommended)
- Free disk space: at least 15 GB total (model + logs/cache + working headroom)

### 1) Configure environment

```bash
cp .env.example .env
```

The checked-in `.env.example` is intentionally runnable for local development
and assessment. You can start with it as-is.

Before any production/staging deployment, replace at least:

- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `EMAIL_VERIFICATION_TOKEN_PEPPER`
- `PASSWORD_RESET_TOKEN_PEPPER`
- `RAG_INTERNAL_API_KEY`
- `VITE_STORAGE_KEY`

For local development, keep:

- `COOKIE_SECURE=false`
- `FRONTEND_BASE_URL=http://localhost:3000`
- cloud model vars blank unless you intentionally enable cloud routing

### 2) Start Ollama and model

```bash
ollama pull thewindmom/llama3-med42-8b
ollama serve
```

### 3) Start the stack

```bash
docker compose up -d --build
```

### 4) Open services

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- RAG service: `http://localhost:8001`
- Mailpit UI (local mail capture): `http://localhost:8025`

## Demo users (optional)

If `AUTH_BOOTSTRAP_DEMO_USERS=true`, backend startup seeds GP/Specialist/Admin users using:

- `DEMO_GP_PASSWORD`
- `DEMO_SPECIALIST_PASSWORD`
- `DEMO_ADMIN_PASSWORD`

Default demo emails:

- `gp@example.com`
- `specialist@example.com`
- `admin@example.com`

### First login walkthrough (GP and Specialist)

1. Open `http://localhost:3000`.
2. Sign in as GP or Specialist.
3. If email verification is enabled, open Mailpit (`http://localhost:8025`) and complete verification.
4. GP user:
   - create a new consultation
   - submit first message and wait for AI response stream
   - monitor status changes in consultation list
5. Specialist user:
   - open queue
   - assign one submitted consultation
   - perform review action (`approve`, `request_changes`, or `manual_response`)

## Validated example queries (recommended)

The following prompts were tested repeatedly on March 27, 2026 against the current seeded corpus and consistently returned grounded responses with citations.

1. Specialty: `neurology`  
   Query: `How can migraine aura be distinguished from transient ischaemic attack (TIA) in primary care?`
2. Specialty: `rheumatology`  
   Query: `A patient taking methotrexate has fever and neutropenia. What immediate management steps and referral urgency are recommended?`
3. Specialty: `neurology`  
   Query: `For suspected cauda equina syndrome in primary care, what immediate actions are recommended before urgent transfer?`
4. Specialty: `rheumatology`  
   Query: `In systemic lupus erythematosus with new proteinuria and rising creatinine, what investigations and referral pathway are recommended?`

Direct API example:

```bash
curl -s -X POST http://localhost:8001/ask \
  -H "X-Internal-API-Key: <your-RAG_INTERNAL_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How can migraine aura be distinguished from transient ischaemic attack (TIA) in primary care?",
    "specialty": "neurology",
    "top_k": 5
  }'
```

## Database bootstrap notes

- The root Compose stack mounts SQL bootstrap assets from `rag_service/scripts/db/migrations/`.
- `rag_chunks` seed data is applied only when Postgres initializes a fresh `postgres_data/` directory.
- If you already have existing local DB data, seed/init scripts are not re-run automatically.

## Local service-level development

For deep service-specific workflows and commands:

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)
- [rag_service/README.md](rag_service/README.md)

Service-level env files are also scaffolded:

- `backend/.env.example`
- `frontend/.env.example`
- `rag_service/.env.example`

Each can be copied with:

```bash
cp <service>/.env.example <service>/.env
```

## CI quality gates

### Frontend CI (`.github/workflows/ci-frontend.yml`)

- `npm ci`
- `npm run lint`
- `npm run format:check`
- `npm run typecheck`
- `npm run test:coverage`

### Backend CI (`.github/workflows/ci-backend.yml`)

- `pip install -e ".[dev]"`
- `ruff check src tests`
- `ruff format --check src tests`
- `mypy src`
- `pytest --cov=src --cov-fail-under=90`

### RAG CI (`.github/workflows/ci-rag-service.yml`)

- `pip install -e ".[dev]"`
- `ruff check .`
- `ruff format --check .`
- `mypy src`
- `pytest --cov=src --cov-fail-under=90`

## Current constraints and implementation notes

- Primary clinical specialties currently surfaced in core workflows: neurology and rheumatology.
- File upload limits are enforced (size/count/extensions; backend defaults include 3 MB max file size).
- Chat archive behavior is status-driven (`ChatStatus.ARCHIVED`).
- SSE chat streaming uses an in-process event bus; multi-worker web server configs are intentionally guarded against.
- New-user login behavior depends on email-verification settings (`NEW_USERS_REQUIRE_EMAIL_VERIFICATION`).

## Priority roadmap (important features to implement)

1. In-app role onboarding and contextual help: GP/Specialist/Admin guided tours and workflow tips directly in the product.
2. Setup doctor and environment validation CLI: one command to validate required env vars, service connectivity, migrations, and model availability.
3. Unified domain enums across frontend/backend/admin: remove severity/status inconsistencies and enforce one shared contract.
4. Stronger production access controls: admin MFA, privileged action re-auth, and session-risk policies.
5. Specialist workload balancing and SLA tooling: queue prioritization, assignment fairness, and escalation timers.
6. RAG quality governance: automated grounding-score checks, citation quality metrics, and regression gates in CI.
7. Operational observability and runbooks: service SLO dashboards, alert routing, and failure playbooks for backend/RAG workflows.
8. Data governance improvements: configurable retention windows, safer archival/export flows, and clearer audit event taxonomy.

# Ambience AI 1.5 — Finalization Plan

> **Starting point:** `main` branch
> **Reference:** `feature/rag-updates` (use as inspiration, don't merge)
> **Date:** 2026-03-19
> **Goal:** Ship a deployable, reviewed, tested product

---

## Table of Contents

1. [Current State: Main vs Rag-Updates](#1-current-state-main-vs-rag-updates)
2. [Feature Audit (Your 17-Item List)](#2-feature-audit-your-17-item-list)
3. [Code Review Findings Status (PDF Review)](#3-code-review-findings-status-pdf-review)
4. [File Structure Comparison](#4-file-structure-comparison)
5. [Code Quality Setup (What Main Is Missing)](#5-code-quality-setup-what-main-is-missing)
6. [Implementation Roadmap](#6-implementation-roadmap)

---

## 1. Current State: Main vs Rag-Updates

### What Main Already Has (that's solid)
- Full auth flow: login, register, JWT tokens
- Email verification (signup + resend)
- Password reset (forgot + confirm)
- SMTP integration (mailpit for dev)
- Repository pattern (user, chat, message, notification, audit, email verification, password reset)
- Chat RBAC via `chat_policy.py` (centralized, no scattered role checks)
- Redis cache with TTL (chat list 30s, detail 60s, profile 300s)
- SSE streaming for AI generation (in-process pub/sub with replay)
- Notification system (types, mark read, bulk read)
- File upload handling (size limit, extension check)
- Admin panel (stats, user CRUD, chat management, audit logs)
- RAG pipeline: hybrid vector + keyword search, RRF fusion, reranking, citation tracking
- LLM routing (local 8B vs cloud 70B with score threshold)
- Retry queue (RQ + Redis worker)
- 29 backend tests, 23 frontend tests (vitest + MSW + playwright config), 36 RAG tests
- Specialist workflow (queue, assign, review)
- Patient context fields (age, gender, notes)
- Docker Compose: 7 services (mailpit, redis, postgres, backend, rag_service, rag_worker, frontend)

### What Rag-Updates Added Over Main
| Feature | Details | Worth Porting? |
|---------|---------|----------------|
| **Global rate limiting** | `core/rate_limit.py` — sliding window, IP-based, Redis-backed, graceful degradation | YES — critical for security |
| **Cache invalidation service** | `services/cache_invalidation.py` — centralized invalidation on mutations | YES — prevents stale data |
| **Refresh tokens** | Access (30min) + refresh (7 days) with cookie rotation | YES — better auth UX |
| **Session versioning** | `session_version` on User — logout invalidates all old JWTs | YES — critical for security |
| **DB models split** | One file per model instead of monolith `models.py` | NICE-TO-HAVE — cleaner but not urgent |
| **API endpoints/ subdir** | Routes in `api/endpoints/` with centralized `router.py` | NICE-TO-HAVE |
| **Alembic migrations** | Proper versioned migrations instead of raw ALTER TABLEs in `main.py` | YES — the current `main.py` with 200+ lines of ALTER TABLE is fragile |
| **DB bootstrap module** | Separate `db/bootstrap.py` for demo users + migration | YES — cleaner separation |
| **RAG orchestration refactor** | `rag/` → `orchestration/` package | NICE-TO-HAVE |
| **RAG config split** | Single `config.py` → `config/{base,llm,runtime,storage}.py` | NICE-TO-HAVE |
| **RAG jobs package** | `retry_queue.py` → `jobs/{retry,state,responses}.py` | NICE-TO-HAVE |
| **RAG citations module** | `api/citations.py` — extraction, grouping, validation | YES — fixes citation bugs |
| **RAG API services layer** | `api/services.py` — chunk filtering, evidence selection | YES — cleaner than inline |
| **Telemetry utility** | `utils/telemetry.py` for metrics recording | NICE-TO-HAVE |
| **Frontend utilities split** | 15+ utility modules in `utils/` | NICE-TO-HAVE |
| **Frontend AuthContext split** | Context + hook separation | NICE-TO-HAVE |
| **Makefiles** | Backend + rag_service build helpers | NICE-TO-HAVE |
| **More tests** | 42 backend, 47 frontend, 49 RAG (vs 29/23/36 on main) | YES — write your own, don't copy |

---

## 2. Feature Audit (Your 17-Item List)

| # | Feature | Main? | Rag-Updates? | What's Needed |
|---|---------|-------|-------------|---------------|
| 0 | **Edit Response + sources form** | PARTIAL — specialist can review/approve/reject, but no inline edit with source field form | PARTIAL — same | Build: inline edit form on specialist detail page with editable sources section |
| 1 | **Gender and Age Fields** | YES — `patient_age`, `patient_gender` on Chat model + `patient_context` JSONB | YES | Done on main |
| 2 | **File Upload for queries + manual response** | YES — `POST /chats/{id}/files`, FileAttachment model, text extraction | YES | Done on main (verify frontend file upload UI works) |
| 3 | **Dashboard for metrics** | YES — `GET /admin/stats` returns counts; `AdminDashboardPage.tsx` with Recharts | YES | Partially done — expand with more metrics (response times, RAG accuracy, etc.) |
| 4 | **Integrate RAG logs to admin panel** | PARTIAL — AuditLog captures RAG queries, `AdminLogsPage.tsx` exists | PARTIAL | Need: surface RAG-specific telemetry (model used, retrieval scores, latency) in admin panel |
| 5 | **Swap to 70B model** | YES — LLM routing with `LLM_ROUTE_THRESHOLD`, cloud Med42-70B configured | YES | Done — routing logic exists. Verify RunPod endpoint is active. |
| 6 | **Manual document upload (admin)** | YES — `POST /ingest` endpoint + `AdminGuidelinesPage.tsx` | YES | Done on main |
| 7 | **Filter by specialty** | PARTIAL — `specialty` field on Chat + source filtering in RAG | PARTIAL | Need: frontend specialty filter dropdown on queries list pages |
| 8 | **Regenerate response** | NO — no endpoint or UI | NO | Build: `POST /chats/{id}/regenerate` endpoint + frontend button |
| 9 | **Retry Queue** | YES — RQ worker + Redis, `retry_queue.py` | YES (better structured) | Done on main |
| 10 | **Cache for data** | YES — RedisCache with TTL, `utils/cache.py` | YES (+ invalidation service) | Port: cache invalidation service from rag-updates |
| 11 | **Integrate dates to citations** | NO — citations have page_start/end but no dates | NO | Build: add `published_date` to citation metadata during ingestion, surface in API response |
| 12 | **Citation docs bug** | UNKNOWN — need to test | HAS FIX ATTEMPT — `api/citations.py` + `api/services.py` | Investigate: check if in-text citations match sources section. Likely related to `source_path`/`source_url` confusion (M4 in review) |
| 13 | **Email Verification** | YES — full flow with token, resend, rate limiting | YES | Done on main |
| 14 | **Password Reset** | YES — forgot + confirm + rate limiting | YES | Done on main |
| 15 | **2FA (optional)** | NO | NO | Build: TOTP-based 2FA (pyotp), QR code setup, verify on login |
| 16 | **Integration Tests** | PARTIAL — some in backend/tests but use direct DB insertion (T8 in review) | PARTIAL | Build: proper integration tests that go through API endpoints |
| 17 | **E2E tests (user stories)** | NO — Playwright config exists but no test files | NO | Build: Playwright tests for key flows (GP query → AI → Specialist review → Approval) |

### Summary: What Still Needs Building
- **Edit Response with sources form** (feature 0)
- **Regenerate response** (feature 8)
- **Dates in citations** (feature 11)
- **Citation bug fix** (feature 12)
- **2FA** (feature 15)
- **Integration tests** (feature 16 — rewrite properly)
- **E2E tests** (feature 17)
- **Specialty filter on frontend** (feature 7 — backend exists)
- **Expanded dashboard metrics** (feature 3 — basic exists)
- **RAG logs in admin** (feature 4 — partial)

---

## 3. Code Review Findings Status (PDF Review)

The PDF review was done against `rag-updates`. Here's what applies to `main`:

### Critical Issues

| # | Issue | Status on Main | Action |
|---|-------|---------------|--------|
| C1 | Demo users auto-created with `password123` | **PRESENT** — `main.py:120` defaults to `AUTH_BOOTSTRAP_DEMO_USERS=true` | FIX: Default to `false`, only enable with explicit env var |
| C2 | SECRET_KEY defaults to known string, no startup block | **PRESENT** — `config.py:14` has `TEST_SECRET_KEY_DO_NOT_USE_IN_PROD` | FIX: Raise error on startup if SECRET_KEY is the default |
| C3 | RAG service has zero auth on all endpoints | **PRESENT** — `rag_service/src/api/routes.py` has no auth | FIX: Add shared secret / API key auth between backend→rag_service |
| C4 | JWT in URL query param for SSE | **PRESENT** — `chats.py:132` uses `?token=` | FIX LATER: Use a short-lived opaque SSE ticket instead of the main JWT |

### High Severity

| # | Issue | Status on Main | Action |
|---|-------|---------------|--------|
| H1 | Rate limiting disabled when Redis down | **NOT APPLICABLE** — main has NO global rate limiting at all | FIX: Add rate limiting (port from rag-updates), with fallback |
| H2 | session_version not on SSE path | **NOT APPLICABLE** — main has NO session_version | FIX: Add session_version (port from rag-updates) |
| H3 | File read fully into memory before size check | **LIKELY PRESENT** — check `chat_service.py` file upload | FIX: Stream-check file size before reading |
| H4 | Extension check on filename only, no MIME | **PRESENT** — extension-only validation | FIX: Add python-magic or filetype library for MIME detection |
| H5 | Hardcoded passwords in docker-compose | **PRESENT** — `team20_password` for Postgres, HF API key in plain text | FIX: Move to `.env` file, add `.env.example` template |
| H6 | Password reset has no email verification token | **NEEDS CHECK** — main has token-based reset, verify it's properly secured | VERIFY: Check `auth_service.py` reset flow |
| H7 | File content silently truncated at 8000 chars | **UNKNOWN** — check if main has this | CHECK: Look at RAG context building |
| H8 | Revision failure is silent | **UNKNOWN** — check specialist review flow | CHECK: Look at `specialist_service.py` |

### Medium — Architectural Debt

| # | Issue | Status on Main | Action |
|---|-------|---------------|--------|
| M1 | Two diverged answer paths (/answer + /ask) | **NOT ON MAIN** — main has single `/ask` endpoint | OK — main is cleaner |
| M2 | SSE event bus is in-process singleton | **PRESENT** — `utils/sse.py` | ACCEPT for now — single worker is fine for pilot |
| M3 | Mixed concurrency (asyncio + threading) | **NEEDS CHECK** | CHECK: Look at chat_service.py |
| M4 | source_path set to source_url value | **NEEDS CHECK** — may be the citation bug (feature 12) | CHECK + FIX |
| M5 | Multi-gate chunk filter discards chunks missing URLs | **NEEDS CHECK** | CHECK |
| M6 | Async Redis cache has sync bridge on daemon thread | **NEEDS CHECK** — `utils/cache.py` | CHECK |
| M7 | Rate limiting is IP-only | **NO RATE LIMITING** on main at all | FIX: When adding rate limiting, key on IP + user_id |
| M8 | CORS allows all origins | **PRESENT** — `main.py:219-224` has `allow_origins=["*"]` | FIX: Configure per environment |
| M9 | O(n^2) dedup in reranker | **NEEDS CHECK** — look at `retrieval/rerank.py` | CHECK |
| M10 | No specialist assignment algorithm | **PRESENT** — manual assignment only | ACCEPT for now |

### Low — Ops & Observability

| # | Issue | Status on Main | Action |
|---|-------|---------------|--------|
| L1 | No `restart: always` on most services | **PRESENT** — only `db_vector` has restart policy | FIX: Add `restart: unless-stopped` to all services |
| L2 | Stack stays down after reboot | **PRESENT** | FIX: Same as L1 |
| L3 | Redis has no `maxmemory` limit | **PRESENT** | FIX: Add `command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru` |
| L4 | No healthcheck for rag_service | **PRESENT** | FIX: Add healthcheck to rag_service in compose |
| L5 | rag_worker has no graceful drain | **PRESENT** | ACCEPT for now |
| L6 | Telemetry files in ephemeral filesystem | **PRESENT** | FIX: Add volume mount for logs |
| L7 | No structured logging | **PRESENT** | ACCEPT for now — add in future |
| L8 | LLM fallback not alerted | **PRESENT** | ACCEPT for now |
| L9 | Three README files | **PRESENT** — README.md + README.txt + README_Cloud_Hosting_Daniel.md | FIX: Consolidate into one |

### Testing Gaps (all apply to main)

| # | Gap | Priority |
|---|-----|----------|
| T1 | Zero tests for `security.py` | HIGH — write these |
| T2 | Zero tests for `chat_policy.py` RBAC | MEDIUM — main has `test_chat_policy.py` already! Check coverage |
| T3 | Zero frontend tests | DONE on main — 23 test files exist |
| T4 | No test for SSE replay buffer | MEDIUM |
| T5 | No test for RedisCache TTL/key scoping | LOW — main has 14 cache test files |
| T6 | No test for rate limiter | N/A — no rate limiter on main yet |
| T7 | No test for file upload security | MEDIUM — main has `test_file_upload.py`, verify coverage |
| T8 | Integration test uses direct DB insertion | HIGH — rewrite using API calls |
| T9 | No test for LLM routing thresholds | MEDIUM |
| T10 | No E2E test | HIGH — write Playwright tests |

---

## 4. File Structure Comparison

### Main (current)
```
backend/
├── src/
│   ├── main.py                    ← 249 lines, includes ALTER TABLEs + bootstrap
│   ├── api/
│   │   ├── auth.py, chats.py, specialist.py
│   │   ├── admin.py, notifications.py, rag.py
│   │   ├── deps.py, health.py
│   ├── core/
│   │   ├── config.py, security.py
│   │   ├── chat_policy.py         ← GOOD: centralized RBAC
│   ├── db/
│   │   ├── models.py              ← monolith (all models)
│   │   ├── email_verification_models.py
│   │   ├── password_reset_models.py
│   │   ├── session.py, base.py, utils.py
│   ├── repositories/              ← GOOD: data access layer
│   │   ├── user, chat, message, notification
│   │   ├── audit, email_verification, password_reset
│   ├── schemas/
│   │   ├── auth, chat, notification, token, admin
│   ├── services/
│   │   ├── auth, chat, notification, admin
│   │   ├── specialist, email, _mappers
│   ├── utils/
│       ├── cache.py, sse.py, logging.py
├── tests/ (29 files)
├── alembic/ (1 migration)

rag_service/
├── src/
│   ├── main.py, config.py
│   ├── retry_queue.py
│   ├── api/
│   │   ├── app.py, routes.py
│   │   ├── dependencies.py, schemas.py
│   ├── rag/
│   │   ├── pipeline.py, generate.py, prompt.py
│   ├── ingestion/ (10 files)
│   ├── retrieval/ (10 files)
│   ├── generation/
│   │   ├── client.py, router.py, prompts.py, streaming.py
│   ├── utils/
│       ├── db.py, logger.py
├── tests/ (36 files)
├── configs/, scripts/, data/

frontend/
├── src/
│   ├── api/client.ts
│   ├── components/ (19 components)
│   ├── contexts/AuthContext.tsx
│   ├── hooks/useChatStream.ts
│   ├── pages/ (auth, gp, specialist, admin — 29 files)
│   ├── services/ (api.ts, api.streaming.ts)
│   ├── types/, utils/
│   ├── test/ (setup, mocks)
├── playwright.config.ts
```

### Rag-Updates (reference only)
```
Key structural differences:
├── backend/src/api/endpoints/     ← routes in subdirectory
├── backend/src/api/router.py      ← centralized router
├── backend/src/core/rate_limit.py ← NEW: rate limiting
├── backend/src/db/bootstrap.py    ← NEW: separate bootstrap
├── backend/src/db/models/         ← split into individual files
├── backend/src/services/cache_invalidation.py  ← NEW
├── backend/src/services/chat_uploads.py        ← NEW: dedicated upload service
├── backend/src/services/rag_context.py         ← NEW
├── backend/src/services/specialist_review.py   ← NEW: 650 lines
├── rag_service/src/api/ask_routes.py     ← NEW
├── rag_service/src/api/citations.py      ← NEW
├── rag_service/src/api/services.py       ← NEW
├── rag_service/src/api/streaming.py      ← NEW
├── rag_service/src/api/startup.py        ← NEW
├── rag_service/src/config/               ← split config
├── rag_service/src/jobs/                 ← structured retry
├── rag_service/src/orchestration/        ← refactored from rag/
├── rag_service/src/utils/telemetry.py    ← NEW
├── frontend/tests/                       ← tests in separate dir
├── frontend/src/utils/ (15+ modules)     ← split utilities
```

---

## 5. Code Quality Setup (What Main Is Missing)

### RAG Service — Already Has (keep these)
- Ruff linter (line-length 88, pycodestyle + pyflakes + isort + bugbear + comprehensions + pyupgrade)
- Ruff formatter (replaces Black)
- MyPy type checking (strict: `disallow_untyped_defs`)
- Pytest with coverage reporting (`--cov=src --cov-report=html`)

### Backend — Missing Everything
Main's backend has **zero code quality tooling**. Add these:

1. **Create `backend/pyproject.toml`** with:
   - Ruff (same config as rag_service for consistency)
   - MyPy
   - Pytest + coverage settings

2. **Create `backend/.pre-commit-config.yaml`** (optional but recommended):
   ```yaml
   repos:
     - repo: https://github.com/astral-sh/ruff-pre-commit
       rev: v0.4.0
       hooks:
         - id: ruff
           args: [--fix]
         - id: ruff-format
   ```

3. **Add to `backend/requirements-dev.txt`**:
   ```
   ruff>=0.4.0
   mypy>=1.7.0
   pre-commit>=3.0.0
   ```

### Frontend — Has ESLint (keep it)
- ESLint config exists (`eslint.config.js`)
- Vitest configured with MSW mocks
- Playwright config exists (needs test files)

### CI/CD
- RAG service has `.github/workflows/ci.yml`
- Backend and frontend have NO CI — add workflows

---

## 6. Implementation Roadmap

Work in this order. Each phase builds on the previous. Every task should be a separate branch + PR.

### Phase 0: Cleanup & Hardening (do first, ~1-2 days)

These are quick wins that make everything else safer.

- [ ] **0.1** Fix `SECRET_KEY` — add startup validation in `main.py` that raises if SECRET_KEY equals the default in non-dev environments
- [ ] **0.2** Fix demo users — change `AUTH_BOOTSTRAP_DEMO_USERS` default to `false` in `main.py:120`
- [ ] **0.3** Fix CORS — replace `allow_origins=["*"]` with configurable `ALLOWED_ORIGINS` env var
- [ ] **0.4** Fix docker-compose secrets — move `POSTGRES_PASSWORD`, `SMTP_PASSWORD`, `CLOUD_LLM_API_KEY` to `.env` file, add `.env.example`
- [ ] **0.5** Fix docker restart policies — add `restart: unless-stopped` to all services
- [ ] **0.6** Fix Redis memory — add `command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru`
- [ ] **0.7** Add rag_service healthcheck in docker-compose
- [ ] **0.8** Consolidate READMEs into one
- [ ] **0.9** Clean up `main.py` — extract the ALTER TABLE migration logic into a proper startup module (inspired by rag-updates' `bootstrap.py`)

### Phase 1: Security (do second, ~2-3 days)

- [ ] **1.1** Add global rate limiting — port `core/rate_limit.py` from rag-updates, key on IP + user_id, with Redis fallback
- [ ] **1.2** Add session versioning — add `session_version` column to User, increment on logout/password change, validate in JWT decode
- [ ] **1.3** Add RAG service auth — shared API key between backend and rag_service (env var `RAG_API_KEY`), validate on every rag_service endpoint
- [ ] **1.4** Fix file upload security — stream-check size before reading into memory (H3), add MIME type detection with `python-magic` (H4)
- [ ] **1.5** Add refresh tokens — short-lived access token (30min) + longer refresh token (7 days), cookie-based rotation
- [ ] **1.6** Fix SSE token leak — replace `?token=` with short-lived opaque ticket (generate ticket → store in Redis with 30s TTL → validate and delete on SSE connect)

### Phase 2: Code Quality Setup (~1 day)

- [ ] **2.1** Create `backend/pyproject.toml` with ruff + mypy + pytest config (copy from rag_service, adjust paths)
- [ ] **2.2** Run `ruff check --fix` on backend code, fix remaining issues
- [ ] **2.3** Run `ruff format` on backend code
- [ ] **2.4** Add `Makefile` for backend with targets: `lint`, `format`, `test`, `typecheck`
- [ ] **2.5** Add GitHub Actions CI for backend (lint + test on PR)
- [ ] **2.6** Add GitHub Actions CI for frontend (lint + test on PR)

### Phase 3: Bug Fixes (~1-2 days)

- [ ] **3.1** Fix citation bug (feature 12) — investigate `source_path` vs `source_url` confusion (review issue M4). Check if in-text citations reference the correct documents in the sources section
- [ ] **3.2** Add cache invalidation service — port from rag-updates, centralize invalidation logic so mutations don't serve stale data
- [ ] **3.3** Fix file content truncation (H7) — if RAG context truncates uploaded file content at 8000 chars, warn the user or chunk properly

### Phase 4: Missing Features (~3-5 days)

- [ ] **4.1** Regenerate response
  - Backend: `POST /chats/{chat_id}/regenerate` — re-query RAG, create new AI message, stream via SSE
  - Frontend: "Regenerate" button on AI messages
- [ ] **4.2** Edit response with sources form (specialist)
  - Backend: `PATCH /chats/{chat_id}/messages/{msg_id}` — allow specialist to edit AI response text + sources
  - Frontend: Inline edit modal on specialist detail page with editable text area + sources form fields
- [ ] **4.3** Specialty filter on frontend
  - Add dropdown filter to `GPQueriesPage`, `SpecialistQueriesPage`, `AdminChatsPage`
  - Backend already supports `specialty` field on Chat
- [ ] **4.4** Dates in citations
  - Ingestion: Extract `published_date` from PDF metadata or document content during ingestion, store in chunk metadata
  - API: Include `published_date` in citation response schema
  - Frontend: Display date in citation cards
- [ ] **4.5** Expanded dashboard metrics
  - Backend: Add metrics to `GET /admin/stats` — average response time, RAG query count, model distribution (local vs cloud), top specialties
  - Frontend: Add charts to `AdminDashboardPage` (already has Recharts)
- [ ] **4.6** RAG logs in admin panel
  - Store RAG telemetry (query, model used, retrieval scores, latency, chunk count) in a `rag_logs` table
  - `GET /admin/rag-logs` endpoint with pagination + filtering
  - Frontend: New section in admin panel or extend `AdminLogsPage`

### Phase 5: 2FA (~2 days)

- [ ] **5.1** Backend: Add TOTP support
  - Install `pyotp` + `qrcode`
  - Add `totp_secret` and `totp_enabled` to User model
  - `POST /auth/2fa/setup` — generate secret, return QR code URI
  - `POST /auth/2fa/verify` — verify TOTP code, enable 2FA
  - `POST /auth/2fa/disable` — disable with password confirmation
  - Modify login flow: if 2FA enabled, return `requires_2fa: true`, require code in second step
- [ ] **5.2** Frontend: 2FA setup UI
  - Profile page: toggle 2FA, show QR code, verify setup code
  - Login page: conditional 2FA code input

### Phase 6: Testing (~3-5 days)

- [ ] **6.1** Write `security.py` unit tests — JWT creation, expiry, session_version validation, cookie handling (T1)
- [ ] **6.2** Expand `test_chat_policy.py` — verify all RBAC rules are covered (T2)
- [ ] **6.3** Write rate limiter tests — normal flow, Redis failure fallback, IP + user_id keying (T6)
- [ ] **6.4** Write file upload security tests — extension bypass attempts, oversize files, path traversal (T7)
- [ ] **6.5** Rewrite integration tests — use API calls instead of direct DB insertion (T8)
- [ ] **6.6** Write LLM routing threshold tests (T9)
- [ ] **6.7** Write SSE replay buffer test (T4)
- [ ] **6.8** Write Playwright E2E tests (T10):
  - GP creates query → AI streams response → GP views response with citations
  - Specialist views queue → assigns chat → reviews → approves/rejects
  - Admin views dashboard → manages users → views logs
  - Auth flows: register → verify email → login → forgot password → reset
  - File upload flow

### Phase 7: Final Polish (~1-2 days)

- [ ] **7.1** Run full test suite, fix failures
- [ ] **7.2** Run ruff + mypy across all Python code, fix issues
- [ ] **7.3** Review all env vars — ensure `.env.example` files are complete and accurate
- [ ] **7.4** Test Docker Compose full stack from clean state
- [ ] **7.5** Write final README with setup instructions, architecture overview, env var reference

---

## Quick Reference: What to Port from Rag-Updates

When implementing the phases above, refer to these files on `feature/rag-updates` for inspiration (don't copy-paste — understand and rewrite):

| What | File on rag-updates |
|------|-------------------|
| Rate limiting | `backend/src/core/rate_limit.py` |
| Session versioning | `backend/src/db/models/user.py` (look for `session_version`), `backend/src/core/security.py` |
| Cache invalidation | `backend/src/services/cache_invalidation.py` |
| Refresh tokens | `backend/src/core/security.py`, `backend/src/core/config.py` |
| Citation fixes | `rag_service/src/api/citations.py`, `rag_service/src/api/services.py` |
| File upload service | `backend/src/services/chat_uploads.py` |
| Bootstrap module | `backend/src/db/bootstrap.py` |

To view any file on rag-updates without switching branches:
```bash
git show feature/rag-updates:backend/src/core/rate_limit.py
```

---

## Estimated Total: ~15-20 working days

- Phase 0 (cleanup): 1-2 days
- Phase 1 (security): 2-3 days
- Phase 2 (code quality): 1 day
- Phase 3 (bug fixes): 1-2 days
- Phase 4 (features): 3-5 days
- Phase 5 (2FA): 2 days
- Phase 6 (testing): 3-5 days
- Phase 7 (polish): 1-2 days

You don't have to do it all at once. Phases 0-2 make the project solid. Phase 3-4 complete the features. Phase 5-7 make it production-ready.

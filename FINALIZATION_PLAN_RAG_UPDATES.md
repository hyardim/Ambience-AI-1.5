# Ambience AI 1.5 — Finalization Plan (feature/rag-updates)

> **Branch:** `feature/rag-updates` (with `main` merged in)
> **Date:** 2026-03-19
> **Goal:** Ship a deployable, reviewed, tested product

---

## Table of Contents

1. [Merge Status](#1-merge-status)
2. [Critical Bugs — Must Fix Before Anything Else](#2-critical-bugs--must-fix-before-anything-else)
3. [Full Code Review Findings](#3-full-code-review-findings)
4. [Feature Checklist (17-Item List)](#4-feature-checklist-17-item-list)
5. [Test Coverage Assessment](#5-test-coverage-assessment)
6. [PDF Code Review Findings Status](#6-pdf-code-review-findings-status)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Merge Status

**Completed:** Main merged into feature/rag-updates. All 18 conflicts resolved.

| Area | Conflicts Resolved | Strategy |
|------|-------------------|----------|
| backend/Dockerfile | 1 | Combined: rag-updates' appuser security + main's alembic migration |
| backend/alembic/* | 3 | Combined: rag-updates' config imports + main's migration files |
| frontend/src/services/api.ts | 1 (complex) | Kept rag-updates' cookie-based auth + main's SSE function signature |
| frontend/src/pages/* | 3 | Kept rag-updates' refactored versions with utility functions |
| frontend/src/contexts/AuthContext.tsx | 1 | Kept rag-updates' split context with localStorage helpers |
| frontend/src/components/ErrorBoundary.tsx | 1 | Kept rag-updates' version with fallback prop |
| frontend/src/App.tsx | 1 | Kept rag-updates' Suspense + LoadingScreen |
| frontend/.gitignore | 1 | Kept rag-updates |
| frontend/tests/support/utils.tsx | 1 | Kept rag-updates (localStorage, not secureStorage) |
| rag_service/scripts/workers/run_retry_worker.py | 1 | Kept rag-updates' config-based Redis URL |
| Deleted files | 4 | Confirmed: requirements.txt, db/models.py, api/client.ts, GPNewQueryPage.test.tsx |

**Duplicate " 2" files:** Cleaned up in node_modules, .venv, __pycache__, htmlcov.

---

## 2. Critical Bugs — Must Fix Before Anything Else

These are blocking issues that will prevent the app from running correctly.

### BUG-1: SSE Streaming Is Broken (CRITICAL)

**Problem:** `subscribeToChatStream()` in `frontend/src/services/api.ts:572-574` takes 3 params `(chatId, token, handlers)`, but `useChatStream.ts:171` calls it with only 2 params `(chatId, handlers)` — skipping the token.

**Impact:** All real-time chat streaming (GP seeing AI responses, specialist seeing updates) is broken. The EventSource URL won't have authentication.

**Fix options:**
1. **Remove the `token` param** from `subscribeToChatStream` and use cookie auth instead (consistent with rest of rag-updates' auth approach)
2. Or keep the token param and pass it from the hook

**Recommended:** Option 1 — rag-updates uses cookie-based auth everywhere else, so SSE should too. But note the backend SSE endpoint at `backend/src/api/endpoints/chats.py:135-174` currently accepts tokens via query param OR cookie. If using cookies only, ensure the EventSource sends cookies (it does by default for same-origin).

**Files to change:**
- `frontend/src/services/api.ts:572-603` — remove `token` param, update EventSource URL
- `frontend/src/hooks/useChatStream.ts:171` — already passing 2 args, will work after api.ts fix

### BUG-2: SSE Handler Type Mismatches

**Problem:** Multiple type issues in the SSE event handlers:
- `api.ts:595` — `event` is `Event` not `MessageEvent`, so `event.data` doesn't exist on error handler
- `useChatStream.ts:178,202,213` — handler params have implicit `any` types
- Handler callbacks expect different field names than what the backend sends (e.g., `message_id` vs `messageId`)

**Fix:** Cast error event properly. Add explicit types to handler callbacks. Verify field name mapping matches backend SSE events.

### BUG-3: ReviewRequest Type Mismatch

**Problem:** `api.ts:367,384` sends `{ decision, feedback, manual_content, manual_sources }` but the `ReviewRequest` type at `types/api.ts:140-145` defines `{ action, replacement_content, replacement_sources }`.

**Fix:** Align the type definition with what the backend actually expects. Check `backend/src/api/endpoints/chats.py` or `specialist.py` for the actual field names.

### BUG-4: Raw SQL Table Creation Outside Alembic

**Problem:** `backend/src/services/auth_service.py:453-507` creates `password_reset_tokens` and `email_verification_tokens` tables via raw `CREATE TABLE IF NOT EXISTS` SQL at runtime. These tables are NOT in any Alembic migration.

**Impact:** Schema drift — Alembic doesn't know about these tables. Running `alembic upgrade head` won't create them; they only exist if the app has started at least once.

**Fix:** Create a new Alembic migration (`alembic revision -m "add_auth_token_tables"`) that creates these tables, then remove the raw SQL from `auth_service.py`.

---

## 3. Full Code Review Findings

### Backend (42 test files, well-structured)

| Severity | Issue | Location | Action |
|----------|-------|----------|--------|
| CRITICAL | Insecure default SECRET_KEY | `config.py:7,21` | Make SECRET_KEY required (no default) or block startup |
| CRITICAL | Hardcoded DB password in defaults | `config.py:26` | Remove default, require .env |
| HIGH | In-memory rate limiting (bypassed with multiple workers) | `auth_service.py:45-46` | Move to Redis-backed rate limiting |
| HIGH | Empty token peppers | `config.py:83,85` | Generate unique peppers per environment |
| HIGH | Demo users created by default | `bootstrap.py:31,40-62` | Default `AUTH_BOOTSTRAP_DEMO_USERS=false` |
| HIGH | Password reset tokens logged | `email_service.py:60-61,78-79` | Never log tokens |
| HIGH | Migration race condition | `Dockerfile:29` | Run migrations as init step, not every startup |
| MEDIUM | CORS methods/headers too permissive | `main.py:20-26` | Specify explicit methods and headers |
| MEDIUM | SSE endpoint accepts token in query param | `chats.py:135-174` | Remove query param, use cookies only |
| MEDIUM | Cascade delete inconsistency | `chat.py:65-68` vs `notification.py:32` | Decide on consistent strategy |
| MEDIUM | SMTP errors not caught | `email_service.py` | Wrap SMTP calls in try/except |
| LOW | No log rotation configured | `logging.py:4-8` | Add RotatingFileHandler |

### Frontend (6 test files, several broken)

| Severity | Issue | Location | Action |
|----------|-------|----------|--------|
| CRITICAL | SSE streaming broken (see BUG-1) | `api.ts:572` + `useChatStream.ts:171` | Fix function signature |
| CRITICAL | ReviewRequest type mismatch (see BUG-3) | `api.ts:367` vs `types/api.ts:140` | Align types |
| HIGH | SSE error handler type error | `api.ts:594-596` | Cast Event to MessageEvent |
| HIGH | AdminChatResponse missing messages prop | `AdminChatsPage.tsx:102-103` | Fix type or add messages |
| HIGH | API call param mismatches | `SpecialistQueriesPage.tsx:44-45` | Fix function signatures |
| HIGH | Test files reference non-existent modules | `auth/*.test.tsx` | Fix import paths |
| MEDIUM | 51 TypeScript errors reported | Various | Run `npx tsc --noEmit` and fix |

### RAG Service (50 test files, excellent quality)

| Severity | Issue | Location | Action |
|----------|-------|----------|--------|
| CRITICAL | No auth on ANY endpoint | `routes.py`, `ask_routes.py` | Add API key auth |
| HIGH | Duplicate citation code | `citations.py` + `jobs/responses.py` | Consolidate into shared module |
| HIGH | Two answer endpoints (/answer + /ask) | `routes.py:151` + `ask_routes.py:43` | Document or consolidate |
| MEDIUM | Broad `except Exception` catches | `routes.py:249,358` | Catch specific exceptions |
| MEDIUM | No health check in docker-compose | `docker-compose.yml` | Add healthcheck |
| LOW | Hardcoded routing thresholds | `router.py` | Document thresholds |

### Docker & Integration

| Severity | Issue | Location | Action |
|----------|-------|----------|--------|
| CRITICAL | Hardcoded passwords (team20_password) | `backend/.env:7`, `rag_service/.env:6,8` | Move to .env.example, gitignore .env |
| CRITICAL | Hardcoded SMTP fallback password | `docker-compose.yml:65` | Remove fallback |
| HIGH | No restart policies on 6/7 services | `docker-compose.yml` | Add `restart: unless-stopped` |
| HIGH | No health checks on 6/7 services | `docker-compose.yml` | Add healthchecks |
| HIGH | depends_on without conditions | `docker-compose.yml:91-93` | Add `service_healthy` conditions |
| MEDIUM | Redis no maxmemory | `docker-compose.yml` | Add memory limit |
| MEDIUM | .env files have localhost URLs | `backend/.env`, `rag_service/.env` | Document dev vs Docker differences |

---

## 4. Feature Checklist (17-Item List)

| # | Feature | Status on rag-updates (merged) | What's Still Needed |
|---|---------|-------------------------------|---------------------|
| 0 | Edit Response + sources form | PARTIAL — specialist can review/approve/reject/manual_response with sources | Build inline edit UI on specialist detail page |
| 1 | Gender and Age Fields | DONE — `patient_age`, `patient_gender`, `patient_notes` on Chat model | — |
| 2 | File Upload for queries + manual response | DONE — upload endpoint + frontend file picker + specialist manual response with files | Verify file upload UI works end-to-end |
| 3 | Dashboard for metrics | PARTIAL — `GET /admin/stats` + `AdminDashboardPage` with Recharts | Expand: response times, RAG accuracy, model distribution |
| 4 | RAG logs in admin panel | PARTIAL — AuditLog captures queries, AdminLogsPage exists | Surface RAG telemetry (model, scores, latency) in admin |
| 5 | Swap to 70B model | DONE — LLM routing with threshold, cloud Med42-70B configured | Verify RunPod endpoint is active |
| 6 | Manual document upload (admin) | DONE — `POST /ingest` + AdminGuidelinesPage | — |
| 7 | Filter by specialty | PARTIAL — `specialty` on Chat + RAG filtering | Build frontend dropdown filter on query list pages |
| 8 | Regenerate response | NOT DONE | Build `POST /chats/{id}/regenerate` + frontend button |
| 9 | Retry Queue | DONE — RQ worker + Redis, structured jobs package | — |
| 10 | Cache for data | DONE — RedisCache + cache invalidation service | — |
| 11 | Dates in citations | NOT DONE | Add `published_date` to ingestion metadata, surface in API |
| 12 | Citation docs bug | HAS FIX — `citations.py` + `services.py` with chunk filtering | Test end-to-end, verify source_path/source_url handling |
| 13 | Email Verification | DONE — full flow with token, resend, rate limiting | — |
| 14 | Password Reset | DONE — forgot + confirm + rate limiting | — |
| 15 | 2FA (optional) | NOT DONE | Build TOTP-based 2FA (pyotp + QR code) |
| 16 | Integration Tests | PARTIAL — some exist but use direct DB | Rewrite using API calls |
| 17 | E2E tests (user stories) | NOT DONE — Playwright config exists, no test files | Write Playwright tests |

### Still Needs Building (7 items):
1. **Regenerate response** (feature 8)
2. **Dates in citations** (feature 11)
3. **2FA** (feature 15)
4. **E2E tests** (feature 17)
5. **Specialty filter frontend** (feature 7 — backend exists)
6. **Expanded dashboard** (feature 3 — basic exists)
7. **RAG logs in admin** (feature 4 — partial)

### Needs Verification (3 items):
1. **Edit response form** (feature 0 — manual_response exists, needs UI polish)
2. **Citation bug** (feature 12 — fix exists, test it)
3. **File upload** (feature 2 — code exists, verify end-to-end)

---

## 5. Test Coverage Assessment

### Backend: 42 test files
**Good coverage:** Auth flows, chat CRUD, file uploads, admin endpoints, specialist workflows, notifications, rate limiting, security.

**Gaps:**
- No tests for `specialist_review.py` (120+ lines of complex logic)
- No tests for `cache_invalidation.py`
- No tests for SSE event generator / replay buffer
- Integration tests use direct DB insertion instead of API calls

### Frontend: 6 test files (several broken)
**Existing:** ErrorBoundary, ForgotPassword, ResendVerification, ResetPassword, VerifyEmail, secureStorage

**Broken tests:**
- Auth test files reference non-existent `../../test/utils` and `../../test/mocks/server`
- Need to verify test setup imports `@testing-library/jest-dom`

**Missing (high priority):**
- API service functions (login, register, chat operations)
- AuthContext provider
- useChatStream hook
- GPQueryDetailPage, SpecialistQueryDetailPage
- Admin pages
- Integration tests for auth flow

### RAG Service: 50 test files (excellent)
**Good coverage:** Ingestion pipeline, retrieval, generation, routing, citations, jobs/retry, API routes, streaming.

**Gaps:**
- `/answer` with `stream=True` end-to-end
- `/revise` with patient_context
- `/health` endpoint
- LLM fallback when primary provider fails
- Citation edge cases (empty answer, no citations)

---

## 6. PDF Code Review Findings Status

### Critical Issues (C1-C4)

| # | Issue | Status on rag-updates | Still Needs Fix? |
|---|-------|-----------------------|-----------------|
| C1 | Demo users auto-created with password123 | FIXED — `AUTH_BOOTSTRAP_DEMO_USERS` defaults to `false` | NO |
| C2 | SECRET_KEY defaults to known string | FIXED — production startup now blocks insecure default | NO |
| C3 | RAG service has zero auth | PRESENT — no auth on any endpoint | YES — add API key auth |
| C4 | JWT in URL query param for SSE | FIXED — SSE stream now uses standard auth dependency and cookies/headers | NO |

### High Severity (H1-H8)

| # | Issue | Status on rag-updates | Still Needs Fix? |
|---|-------|-----------------------|-----------------|
| H1 | Rate limiting disabled when Redis down | FIXED — in-memory fallback added when Redis is unavailable | NO |
| H2 | session_version not on SSE path | FIXED — SSE now uses shared auth dependency path | NO |
| H3 | File read fully into memory before size check | FIXED — bounded chunk read with size enforcement | NO |
| H4 | Extension check only, no MIME validation | FIXED — content validation checks signature/MIME | NO |
| H5 | Hardcoded passwords in docker-compose | FIXED — compose moved to env-based secrets | NO |
| H6 | Password reset missing email verification | FIXED — unverified users cannot request/confirm reset | NO |
| H7 | File content silently truncated at 8000 chars | FIXED — truncation now surfaced to users in stream UX | NO |
| H8 | Revision failure is silent | FIXED — failure now audited and user-notified | NO |

### Medium (M1-M10) — Summary

| Status | Issues |
|--------|--------|
| FIXED by rag-updates | M1 (answer path parity), M4 (source_path metadata bug), M5 (chunk filtering compatibility), M6 (async Redis cache bridge hardening), M7 (rate limiting keys now include session+IP), M8 (CORS policy hardening) |
| STILL PRESENT | M2 (SSE in-process singleton — acceptable for pilot), M3 (mixed concurrency), M9 (O(n^2) rerank dedup), M10 (no specialist auto-assignment) |
| ACCEPTABLE | M2, M10 for pilot |

### Low (L1-L9) — Summary

| Status | Issues |
|--------|--------|
| FIXED by rag-updates | L1-L2 (restart policies), L3 (Redis maxmemory), L4 (rag_service healthcheck), L5 (worker graceful drain), L6 (telemetry/log volumes), L7 (structured JSON logging) |
| STILL PRESENT | L8 (LLM fallback alerting still telemetry-only), L9 (multiple READMEs) |

---

## 7. Implementation Roadmap

### Phase 0: Fix Critical Bugs (DO FIRST — ~1 day)

These must be fixed before the app can run:

- [ ] **0.1** Fix SSE streaming (BUG-1) — remove `token` param from `subscribeToChatStream`, use cookie auth
- [ ] **0.2** Fix SSE handler types (BUG-2) — cast error event, add explicit types, verify field name mapping
- [ ] **0.3** Fix ReviewRequest types (BUG-3) — align `api.ts` with `types/api.ts` and backend expectations
- [ ] **0.4** Fix auth token table migration (BUG-4) — create Alembic migration, remove raw SQL from `auth_service.py`
- [ ] **0.5** Fix broken frontend test imports — update paths to match rag-updates structure
- [ ] **0.6** Run `npx tsc --noEmit` and fix all TypeScript errors

### Phase 1: Security Hardening (~2-3 days)

- [ ] **1.1** Fix SECRET_KEY — raise error on startup if default key is used in non-dev environment
- [ ] **1.2** Fix demo users — change `AUTH_BOOTSTRAP_DEMO_USERS` default to `false`
- [ ] **1.3** Add RAG service auth — shared API key validated on every endpoint via FastAPI dependency
- [ ] **1.4** Fix docker-compose secrets — move all passwords to `.env`, create `.env.example`, gitignore `.env`
- [ ] **1.5** Fix file upload security — stream-check size before reading, add MIME detection
- [ ] **1.6** Fix SSE token leak — remove `?token=` query param support, use cookies only
- [ ] **1.7** Fix password reset token logging — never log tokens, only log that email was sent
- [ ] **1.8** Fix rate limiting — move in-memory dicts to Redis, add fallback for Redis down
- [ ] **1.9** Fix token peppers — generate unique peppers, set via env vars

### Phase 2: Infrastructure Fixes (~1 day)

- [ ] **2.1** Add `restart: unless-stopped` to all docker-compose services
- [ ] **2.2** Add healthchecks for backend, rag_service, redis, frontend
- [ ] **2.3** Add `service_healthy` conditions to all depends_on entries
- [ ] **2.4** Add Redis maxmemory: `command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru`
- [ ] **2.5** Fix CORS — specify explicit methods and headers instead of `["*"]`
- [ ] **2.6** Consolidate READMEs into one
- [ ] **2.7** Add volume mount for telemetry logs

### Phase 3: Code Quality (~1 day)

- [ ] **3.1** Consolidate duplicate citation code (`citations.py` + `jobs/responses.py`) into shared module
- [ ] **3.2** Run `ruff check --fix` + `ruff format` on backend code
- [ ] **3.3** Run `npx eslint --fix` on frontend code
- [ ] **3.4** Add GitHub Actions CI for backend (lint + test on PR)
- [ ] **3.5** Add GitHub Actions CI for frontend (lint + test on PR)
- [ ] **3.6** Document the two RAG answer endpoints (/answer vs /ask) — or consolidate

### Phase 4: Missing Features (~3-5 days)

- [ ] **4.1** Regenerate response
  - Backend: `POST /chats/{chat_id}/regenerate` — re-query RAG, create new AI message, stream via SSE
  - Frontend: "Regenerate" button on AI messages (GP and specialist)
- [ ] **4.2** Specialty filter on frontend
  - Dropdown filter on GPQueriesPage, SpecialistQueriesPage, AdminChatsPage
  - Backend already has `specialty` field on Chat
- [ ] **4.3** Dates in citations
  - Ingestion: extract `published_date` from PDF metadata, store in chunk metadata
  - API: include `published_date` in citation response
  - Frontend: display date on citation cards
- [ ] **4.4** Expanded dashboard metrics
  - Backend: add to `GET /admin/stats` — avg response time, model distribution, top specialties
  - Frontend: add charts (Recharts already installed)
- [ ] **4.5** RAG logs in admin panel
  - Store telemetry in `rag_logs` table (query, model, scores, latency)
  - `GET /admin/rag-logs` with pagination
  - Frontend: new admin page section

### Phase 5: 2FA (~2 days)

- [ ] **5.1** Backend TOTP support
  - Install `pyotp` + `qrcode`
  - Add `totp_secret`, `totp_enabled` to User model
  - Endpoints: `/auth/2fa/setup`, `/auth/2fa/verify`, `/auth/2fa/disable`
  - Modify login: if 2FA enabled, return `requires_2fa: true`
- [ ] **5.2** Frontend 2FA UI
  - Profile page: toggle, QR code, verify setup code
  - Login page: conditional 2FA code input

### Phase 6: Testing (~3-5 days)

- [ ] **6.1** Fix broken frontend tests (auth pages, ErrorBoundary)
- [ ] **6.2** Write frontend tests: API service functions, AuthContext, useChatStream hook
- [ ] **6.3** Write frontend tests: GP and Specialist detail pages
- [ ] **6.4** Write backend tests: specialist_review.py, cache_invalidation.py
- [ ] **6.5** Write backend tests: SSE event generator, replay buffer
- [ ] **6.6** Rewrite integration tests to use API calls instead of direct DB
- [ ] **6.7** Write RAG service tests: streaming endpoint, health check, LLM fallback
- [ ] **6.8** Write Playwright E2E tests:
  - GP creates query → AI streams response → GP views citations
  - Specialist: view queue → assign → review → approve/reject
  - Admin: dashboard → user management → logs
  - Auth: register → verify email → login → password reset
  - File upload flow

### Phase 7: Final Polish (~1-2 days)

- [ ] **7.1** Run full test suite across all 3 services, fix failures
- [ ] **7.2** Run ruff + mypy on all Python code, fix issues
- [ ] **7.3** Run tsc + eslint on frontend, fix issues
- [ ] **7.4** Review all env vars — complete `.env.example` files
- [ ] **7.5** Test Docker Compose full stack from clean state
- [ ] **7.6** Write final README with setup, architecture, env var reference

---

## Estimated Timeline

| Phase | Days | Priority |
|-------|------|----------|
| Phase 0: Critical bugs | 1 | **DO FIRST** |
| Phase 1: Security | 2-3 | **DO SECOND** |
| Phase 2: Infrastructure | 1 | HIGH |
| Phase 3: Code quality | 1 | HIGH |
| Phase 4: Features | 3-5 | MEDIUM |
| Phase 5: 2FA | 2 | MEDIUM |
| Phase 6: Testing | 3-5 | HIGH |
| Phase 7: Polish | 1-2 | MEDIUM |
| **Total** | **~14-20 days** | |

**Minimum viable:** Phases 0-3 (~5-6 days) gets you a working, secure, well-structured app.
**Feature complete:** Add Phase 4-5 (~5-7 more days).
**Production ready:** Add Phase 6-7 (~4-7 more days).

---

## What rag-updates Already Has Over Main (No Porting Needed)

These features are already in the codebase since you're on rag-updates:

- Global rate limiting (`core/rate_limit.py`)
- Cache invalidation service (`services/cache_invalidation.py`)
- Refresh tokens (access 30min + refresh 7 days, cookie-based)
- Session versioning (`session_version` on User model)
- Split DB models (one file per model)
- Structured API endpoints directory
- Alembic migrations (proper versioned)
- DB bootstrap module
- RAG orchestration package
- Split RAG config
- Structured retry jobs package
- Citation parsing module
- RAG API services layer
- Telemetry utilities
- Frontend utilities split (15+ modules)
- Frontend AuthContext split
- Makefiles for backend + rag_service

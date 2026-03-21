# Integration & E2E Test Plan

## Context

The current integration and e2e tests are severely lacking. Backend has 2 integration tests, RAG service has 3, frontend integration has 3, and frontend e2e covers only basic navigation. Critical workflows like the full chat lifecycle, specialist review actions, streaming, error recovery, notifications, admin operations, cross-role access control, and RAG pipeline stages are untested at the integration level. This plan adds **~95 new tests** (15 backend, 34 RAG pipeline, 12 frontend integration, 34 frontend e2e).

## Files to Modify

- `backend/tests/integration/test_workflows.py` — extend with 15 tests
- `rag_service/tests/integration/test_api_flows.py` — extend with 10 tests (API-level)
- `rag_service/tests/integration/test_ingestion_pipeline.py` — NEW, 8 tests
- `rag_service/tests/integration/test_retrieval_pipeline.py` — NEW, 8 tests
- `rag_service/tests/integration/test_generation_pipeline.py` — NEW, 5 tests
- `rag_service/tests/integration/test_orchestration.py` — NEW, 3 tests
- `frontend/tests/integration/app_flows.test.tsx` — extend with 12 tests
- `frontend/e2e/app.spec.ts` — extend with 34 tests

## Key Reusable Infrastructure

- **Backend fixtures** (`backend/tests/conftest.py`): `client`, `db_session`, `registered_gp`, `gp_headers`, `specialist_headers`, `admin_headers`, `created_chat`, `submitted_chat`, `second_gp_headers`, `enable_inline_ai_tasks`
- **RAG test pattern** (`rag_service/tests/integration/test_api_flows.py`): `TestClient(app)`, monkeypatching `routes.retrieve_chunks_advanced`, `routes.generate_answer`, `routes.select_generation_provider`, etc.
- **RAG pipeline modules**: Import real pipeline functions directly, monkeypatch only external I/O (embedding API, vector DB, LLM calls)
- **Frontend integration pattern** (`frontend/tests/integration/app_flows.test.tsx`): `seedAuth()`, `render(<App/>)` with `MemoryRouter`, MSW `server.use()` overrides
- **Frontend e2e helpers** (`frontend/e2e/app.spec.ts`): `installApiMocks(page)`, `setAuthenticatedSession(page, role)`, Playwright `page.goto()` + assertions

---

## 1. Backend Integration Tests (15 tests)

File: `backend/tests/integration/test_workflows.py`

### A. Chat Lifecycle (Critical)

**`test_full_chat_lifecycle_open_to_approved`**
- GP creates chat → sends message (monkeypatch RAG `/answer`) → submits for review → specialist assigns → specialist approves
- Assert: status transitions OPEN→SUBMITTED→ASSIGNED→APPROVED, `reviewed_at` set

**`test_chat_lifecycle_reject_flow`**
- Same setup through assign → specialist rejects with feedback
- Assert: status=rejected, `review_feedback` persisted, GP gets notification

**`test_chat_lifecycle_request_changes_triggers_revision`**
- Assigned chat → specialist calls review with `action=request_changes` → monkeypatch RAG `/revise`
- Assert: status=reviewing, new AI message created from revision, original AI message marked

**`test_submit_only_open_chats`**
- Submit a chat, then try to submit again
- Assert: second submit returns 400

**`test_gp_cannot_edit_chat_after_assignment`**
- Assigned chat → GP tries PATCH title
- Assert: 400

### B. Specialist Per-Message Review (High)

**`test_specialist_per_message_approve`**
- Assigned chat with AI message → specialist reviews specific message with `action=approve`
- Assert: message `review_status=approved`

**`test_specialist_per_message_request_changes`**
- Review specific AI message with `action=request_changes` + feedback → monkeypatch RAG revise
- Assert: original message marked, new revised AI message created

**`test_specialist_sends_message_transitions_to_reviewing`**
- Assigned chat → specialist sends direct message
- Assert: 200, message in chat detail, status auto-transitions to REVIEWING

### C. Multi-User Isolation & Access Control (High)

**`test_gp_cannot_see_other_gps_chats`**
- GP A creates chat → GP B lists chats and tries GET on GP A's chat
- Assert: empty list for GP B, 404 on direct access

**`test_specialist_cannot_assign_wrong_specialty`**
- GP creates rheumatology chat → neurology specialist tries to assign
- Assert: 403

**`test_role_based_endpoint_guards`**
- GP calls specialist endpoints, specialist/GP call admin endpoints
- Assert: 403 for all unauthorized access

### D. Notifications (Medium)

**`test_notifications_created_on_assign_and_review`**
- Full lifecycle (assign + approve) → GP fetches notifications
- Assert: 2 unread notifications with correct types, mark-read works, mark-all-read zeroes count

### E. Admin Operations (Medium)

**`test_admin_stats_reflect_real_data`**
- Create chats across specialties → admin fetches stats
- Assert: counts match created data

**`test_admin_deactivate_user_prevents_login`**
- Admin deactivates GP → GP attempts login
- Assert: login fails

**`test_admin_audit_logs_capture_actions`**
- GP creates chat, sends message → admin fetches logs with filters
- Assert: log entries for create/submit actions

---

## 2. RAG Service Integration Tests (34 tests)

### 2A. Ingestion Pipeline (8 tests)

File: `rag_service/tests/integration/test_ingestion_pipeline.py`

Key modules: `ingestion/extract.py`, `ingestion/clean.py`, `ingestion/sections.py`, `ingestion/tables.py`, `ingestion/metadata.py`, `ingestion/chunker.py`, `ingestion/embed.py`, `ingestion/store.py`

**`test_extract_to_clean_pipeline`**
- Feed raw PDF text (with headers/footers, ligatures, hyphenation) through `extract_text_from_pdf` → `clean_extracted_text`
- Assert: ligatures replaced (ﬁ→fi, ﬂ→fl), hyphenation joined, headers/footers stripped, whitespace normalized
- Reuse: `extract.extract_text_from_pdf` (monkeypatch `pdfplumber.open`), `clean.clean_extracted_text`

**`test_clean_to_section_detect_pipeline`**
- Feed cleaned text → `detect_sections`
- Assert: sections correctly identified with hierarchy (e.g., "1. Introduction" → "1.1 Background"), `section_path` populated
- Reuse: `sections.detect_sections`

**`test_section_to_table_detect_pipeline`**
- Feed text with markdown-style tables → `detect_sections` → `detect_tables`
- Assert: table blocks identified and separated from prose, table metadata attached
- Reuse: `tables.detect_tables`

**`test_metadata_extraction_from_sections`**
- Feed sections → `extract_metadata`
- Assert: document-level metadata (title, authors, date) extracted, section-level metadata populated
- Reuse: `metadata.extract_metadata`

**`test_full_chunking_pipeline`**
- Feed sectioned text → `chunk_document`
- Assert: chunks respect section boundaries, chunk sizes within configured limits, overlap present between consecutive chunks, each chunk carries `section_path` and `metadata`
- Reuse: `chunker.chunk_document`

**`test_embed_chunks_batching`**
- Feed list of chunks → `embed_chunks` (monkeypatch embedding API call)
- Assert: correct batching (batch size respected), all chunks get embedding vectors, dimension matches config
- Reuse: `embed.embed_chunks`, monkeypatch `embed._call_embedding_api`

**`test_store_chunks_to_vector_db`**
- Feed embedded chunks → `store_chunks` (monkeypatch vector DB insert)
- Assert: correct payload format sent to DB, doc_id attached, idempotency (re-store same doc replaces)
- Reuse: `store.store_chunks`, monkeypatch `vector_store.upsert_chunks`

**`test_full_ingestion_extract_to_store`**
- End-to-end: mock PDF bytes → extract → clean → sections → tables → metadata → chunk → embed → store
- Monkeypatch only: `pdfplumber.open`, embedding API, vector DB insert
- Assert: final stored chunks have correct structure (text, embedding, metadata, section_path, doc_id), chunk count reasonable for input size
- This is the critical pipeline integration test

### 2B. Retrieval Pipeline (8 tests)

File: `rag_service/tests/integration/test_retrieval_pipeline.py`

Key modules: `retrieval/query.py`, `retrieval/vector_store.py`, `retrieval/keyword.py`, `retrieval/fusion.py`, `retrieval/filters.py`, `retrieval/rerank.py`, `retrieval/dedup.py`, `api/citations.py`

**`test_query_processing_to_vector_search`**
- Feed raw query → `process_query` → `search_vectors` (monkeypatch DB)
- Assert: query expanded/processed, vector search called with correct embedding and top_k
- Reuse: `query.process_query`, `vector_store.search_vectors`, monkeypatch embedding + DB

**`test_vector_and_keyword_search_parallel`**
- Feed query → run both `search_vectors` and `keyword_search` (monkeypatch both)
- Assert: both return results, results have different ranking characteristics
- Reuse: `vector_store.search_vectors`, `keyword.keyword_search`

**`test_fusion_combines_vector_and_keyword`**
- Feed two result sets → `reciprocal_rank_fusion`
- Assert: RRF scores computed correctly, results merged and re-ranked, no duplicates
- Reuse: `fusion.reciprocal_rank_fusion`

**`test_filters_remove_low_relevance_and_boilerplate`**
- Feed fused results including boilerplate chunks and low-score chunks → apply `filter_results`
- Assert: boilerplate removed (`is_boilerplate` from `api/citations.py`), below-threshold chunks removed, remaining ordered by score
- Reuse: `filters.filter_results`, `citations.is_boilerplate`, `citations.MIN_RELEVANCE`

**`test_rerank_reorders_by_cross_encoder`**
- Feed filtered results → `rerank_results` (monkeypatch cross-encoder model)
- Assert: results reordered based on cross-encoder scores, original scores overwritten
- Reuse: `rerank.rerank_results`, monkeypatch `rerank._score_with_model`

**`test_dedup_removes_near_duplicates`**
- Feed results with near-duplicate text → `deduplicate`
- Assert: only highest-scored version of duplicate content kept
- Reuse: `dedup.deduplicate`

**`test_citation_assembly_from_results`**
- Feed final result set → `extract_citation_results` with mock answer text containing `[1]`, `[2]`, `[3]`
- Assert: citations renumbered correctly, unused citations stripped, used citations match answer references
- Reuse: `citations.extract_citation_results`, `citation_utils.rewrite_citations`

**`test_full_retrieval_query_to_citations`**
- End-to-end: raw query → process → vector search → keyword search → fusion → filter → rerank → dedup → citation assembly
- Monkeypatch only: embedding API, vector DB search, keyword DB search, cross-encoder model
- Assert: final results are filtered, ranked, deduplicated, citation-ready; query_overlap check passes for top results
- This is the critical retrieval pipeline integration test

### 2C. Generation Pipeline (5 tests)

File: `rag_service/tests/integration/test_generation_pipeline.py`

Key modules: `generation/router.py`, `generation/prompts.py`, `generation/client.py`, `generation/streaming.py`

**`test_router_selects_local_for_chunks_only`**
- Feed request with chunks, no file_context → `select_generation_provider`
- Assert: returns `"local"` provider with correct model config
- Reuse: `router.select_generation_provider`

**`test_router_selects_cloud_for_file_context`**
- Feed request with file_context → `select_generation_provider`
- Assert: returns `"cloud"` provider
- Reuse: `router.select_generation_provider`

**`test_prompt_building_includes_all_context`**
- Feed chunks + patient_context + question → `build_prompt` (for answer variant)
- Assert: system prompt contains specialty, chunks formatted with citation markers `[1]`, `[2]`, patient demographics included, question at end
- Reuse: `prompts.build_answer_prompt`

**`test_router_to_client_generates_answer`**
- Router selects provider → build prompt → `generate_answer` (monkeypatch HTTP client)
- Assert: full text response returned, provider-specific headers/URL used
- Reuse: `router.select_generation_provider`, `prompts.build_answer_prompt`, `client.generate_answer`, monkeypatch `httpx.AsyncClient`

**`test_streaming_generation_yields_chunks`**
- Build prompt → `generate_answer_stream` (monkeypatch HTTP SSE stream)
- Assert: yields chunk events in order, final event contains complete text, handles SSE format correctly
- Reuse: `streaming.generate_answer_stream`, monkeypatch `httpx.AsyncClient.stream`

### 2D. Orchestration (3 tests)

File: `rag_service/tests/integration/test_orchestration.py`

Key modules: `api/routes.py` (orchestration logic), all pipeline modules

**`test_orchestration_answer_full_pipeline`**
- POST `/answer` with question + specialty → orchestration calls retrieve → evidence_level → generate
- Monkeypatch: embedding API, vector DB, keyword DB, cross-encoder, LLM HTTP client
- Assert: response has `answer` with citation markers, `citations_used` populated, `citations_retrieved` ≥ `citations_used`
- This tests the full RAG pipeline end-to-end through the API

**`test_orchestration_no_evidence_fallback`**
- POST `/answer` where retrieval returns empty → orchestration skips generation
- Assert: returns canned NO_EVIDENCE_RESPONSE, empty citations

**`test_orchestration_revise_with_feedback`**
- POST `/revise` with previous_answer + feedback + question → retrieval + generation with revision prompt
- Monkeypatch same as answer test
- Assert: response incorporates feedback, citations re-processed

### 2E. API Route Tests (10 tests)

File: `rag_service/tests/integration/test_api_flows.py` (extend existing)

**`test_answer_returns_no_evidence_when_retrieval_empty`**
- Monkeypatch retrieval → `[]`, no file_context → POST `/answer`
- Assert: canned NO_EVIDENCE_RESPONSE, empty citations

**`test_answer_streaming_returns_ndjson_chunks`**
- Monkeypatch retrieval + streaming generation → POST `/answer?stream=true`
- Assert: response lines contain `{"type":"chunk"}` events and final `{"type":"done"}` with citations

**`test_answer_with_patient_context_threads_into_prompt`**
- Capture prompt in fake generate → POST `/answer` with patient_context
- Assert: patient demographics appear in captured prompt

**`test_answer_file_context_only_uses_cloud_provider`**
- Retrieval returns `[]`, file_context provided → capture provider selection
- Assert: cloud provider selected

**`test_answer_retry_on_retryable_generation_error`**
- Monkeypatch `generate_answer` to raise `ModelGenerationError(retryable=True)`
- Assert: 202 with `job_id` and `status` fields

**`test_revise_with_feedback_and_chunks`**
- Monkeypatch retrieval + generation, capture prompt → POST `/revise` with feedback + previous_answer
- Assert: prompt contains feedback text and previous answer

**`test_revise_streaming`**
- Same as answer streaming but via `/revise` endpoint

**`test_query_returns_structured_search_results`**
- Monkeypatch `retrieve_chunks` → POST `/query`
- Assert: 200 with SearchResult objects, correct field mapping

**`test_ingest_rejects_non_pdf_file`**
- POST `/ingest` with `.docx` file
- Assert: 422

**`test_protected_routes_reject_missing_api_key`**
- Set `RAG_INTERNAL_API_KEY` env → POST `/answer` without header
- Assert: 401

---

## 3. Frontend Integration Tests (12 tests)

File: `frontend/tests/integration/app_flows.test.tsx`

### A. GP Chat Flow (Critical)

**`test_gp_consultation_list_renders_chats`**
- seedAuth(gp), push `/gp/queries` → assert both mock chats visible

**`test_gp_chat_detail_shows_messages_and_citations`**
- seedAuth(gp), push `/gp/query/1` → assert user message, AI message, and citation metadata visible

**`test_gp_creates_new_consultation`**
- seedAuth(gp), push `/gp/queries/new` → fill form → submit → assert redirect to detail

**`test_gp_search_filters_consultations`**
- seedAuth(gp), push `/gp/queries` → type in search → assert filtered results

### B. Specialist Flow (Critical)

**`test_specialist_queue_and_assigned_tabs`**
- seedAuth(specialist), push `/specialist/queries` → assert queue items → click assigned tab → assert assigned items

**`test_specialist_chat_detail_shows_review_controls`**
- seedAuth(specialist), push `/specialist/query/1` → assert messages and review buttons visible

### C. Admin Flow (High)

**`test_admin_dashboard_renders_stat_values`**
- seedAuth(admin), push `/admin/dashboard` → assert specific stat numbers from mock

**`test_admin_navigates_all_sections`**
- seedAuth(admin), push `/admin/dashboard` → click through Users, Chats, Logs sidebar links → assert each section renders

### D. Notifications (High)

**`test_notification_dropdown_renders_and_marks_read`**
- seedAuth(gp) → click notification bell → assert items → click mark-read → assert API call

### E. Auth & Error States (Medium)

**`test_register_page_renders_and_submits`**
- Push `/register` (no seed) → fill form → submit → assert redirect

**`test_profile_page_shows_user_info`**
- seedAuth(gp), push `/profile` → assert email and name visible

**`test_api_error_shows_fallback_ui`**
- Override MSW handler to return 500 for chat detail → push `/gp/query/1` → assert error UI

---

## 4. Frontend E2E Tests (34 tests)

File: `frontend/e2e/app.spec.ts`

### A. Authentication & Registration (6 tests)

**`test_login_with_valid_credentials`**
- Navigate to `/login` → fill email+password → submit → assert redirect to role-appropriate dashboard

**`test_login_with_invalid_credentials`**
- Navigate to `/login` → fill wrong credentials → submit → assert error message visible

**`test_register_with_valid_data`**
- Navigate to `/register` → fill all fields (name, email, password, role, specialty) → submit → assert redirect

**`test_register_validation_errors`**
- Navigate to `/register` → submit empty form → assert validation messages for required fields

**`test_forgot_password_flow`**
- Navigate to `/forgot-password` → enter email → submit → assert confirmation message

**`test_logout_clears_session`**
- Login as GP → click logout → assert redirected to login → navigate to `/gp/queries` → assert redirected back to login

### B. GP Workflow (8 tests)

**`test_gp_full_journey_create_to_detail`**
- Login as GP → navigate to new consultation → fill form (specialty, question, patient context) → submit → assert detail page with AI response

**`test_gp_consultation_list_pagination_and_search`**
- Login as GP → view consultation list → assert items rendered → type in search → assert filtered → clear search → assert restored

**`test_gp_views_chat_with_citations`**
- Login as GP → click consultation → assert AI response text and citation titles visible → click citation → assert expanded view

**`test_gp_sends_followup_message`**
- Login as GP → open existing consultation → type followup message → send → assert new message appears with AI response

**`test_gp_submits_chat_for_review`**
- Login as GP → open chat → click submit for review → assert status badge changes to "Submitted" → assert send message disabled

**`test_gp_views_reviewed_feedback`**
- Login as GP → open a rejected chat → assert specialist feedback visible → assert revision prompt shown

**`test_gp_notification_badge_and_list`**
- Login as GP → assert notification bell with count → click bell → assert notification items → click notification → assert navigates to relevant chat

**`test_gp_empty_state_new_user`**
- Login as GP with no chats → assert empty state message → assert "New Consultation" CTA visible

### C. Specialist Workflow (7 tests)

**`test_specialist_views_queue`**
- Login as specialist → assert queue page shows submitted chats filtered by specialty

**`test_specialist_assigns_from_queue`**
- Login as specialist → view queue → click chat → click assign → assert status changes to "Assigned" → assert chat moves to assigned tab

**`test_specialist_reviews_and_approves`**
- Login as specialist → view assigned → click chat → read messages → click approve → assert success toast → assert status "Approved"

**`test_specialist_rejects_with_feedback`**
- Login as specialist → assigned chat → click reject → fill feedback textarea → submit → assert status "Rejected"

**`test_specialist_requests_changes`**
- Login as specialist → assigned chat → click request changes → fill feedback → submit → assert revision generated

**`test_specialist_per_message_review`**
- Login as specialist → assigned chat → hover over AI message → click approve/reject per-message → assert message badge updates

**`test_specialist_sends_direct_message`**
- Login as specialist → assigned chat → type message → send → assert message appears in thread

### D. Admin Operations (6 tests)

**`test_admin_dashboard_stats`**
- Login as admin → assert dashboard shows stat cards with counts (total users, chats, pending reviews)

**`test_admin_user_management`**
- Login as admin → navigate to users → assert user list → search for user → assert filtered → click user → assert detail modal

**`test_admin_deactivate_and_reactivate_user`**
- Login as admin → users page → deactivate a user → assert status badge changes → reactivate → assert restored

**`test_admin_chat_oversight`**
- Login as admin → navigate to chats → assert all chats visible (not scoped by owner) → click chat → assert full detail view

**`test_admin_guidelines_upload`**
- Login as admin → navigate to guidelines → upload PDF file → assert ingestion progress/report

**`test_admin_audit_logs_with_filters`**
- Login as admin → navigate to audit logs → assert entries visible → filter by action type → assert filtered results → filter by date range → assert results

### E. Cross-Role Access Control (4 tests)

**`test_gp_cannot_access_specialist_routes`**
- Login as GP → navigate to `/specialist/queries` → assert redirect to access-denied or dashboard

**`test_specialist_cannot_access_admin_routes`**
- Login as specialist → navigate to `/admin/users` → assert redirect to access-denied

**`test_unauthenticated_redirects_to_login`**
- No login → navigate to `/gp/queries`, `/specialist/queries`, `/admin/dashboard` → assert all redirect to `/login`

**`test_deep_link_preserved_after_login`**
- Navigate to `/gp/query/1` (unauthenticated) → redirected to login → login → assert redirected back to `/gp/query/1`

### F. UI States & Edge Cases (3 tests)

**`test_loading_states_show_skeletons`**
- Login as GP → navigate to consultation list → assert skeleton/loading state visible before data loads

**`test_api_error_shows_error_page`**
- Mock 500 response for chat list → login as GP → assert error fallback UI with retry button → click retry → assert recovery

**`test_mobile_viewport_navigation`**
- Set viewport 375×812 → login as GP → open mobile menu → navigate through sections → assert pages render correctly

---

## Verification

After implementation, run:
```bash
# Backend
cd backend && make check

# RAG Service
cd rag_service && make lint && .venv/bin/python -m pytest --cov=src --cov-fail-under=100

# Frontend unit + integration
cd frontend && npx vitest run

# Frontend e2e
cd frontend && npx playwright test
```

All existing tests must continue to pass. New tests should add ~95 test cases total.

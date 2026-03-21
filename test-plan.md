# Integration & E2E Test Plan Status

This file was originally a backlog of missing integration and e2e coverage.
Those planned items have now been implemented and are no longer listed as TODOs.

## Implemented

- Backend integration workflow coverage added in `backend/tests/integration/test_workflows.py`
	(chat lifecycle, specialist actions, access control, notifications, and admin paths).
- RAG integration pipeline suites added:
	`rag_service/tests/integration/test_ingestion_pipeline.py`,
	`rag_service/tests/integration/test_retrieval_pipeline.py`,
	`rag_service/tests/integration/test_generation_pipeline.py`,
	`rag_service/tests/integration/test_orchestration.py`, and
	expanded `rag_service/tests/integration/test_api_flows.py`.
- Frontend integration coverage expanded in
	`frontend/tests/integration/app_flows.test.tsx`.
- Frontend e2e coverage expanded in `frontend/e2e/app.spec.ts`.

## Current Status

- No outstanding items from the original plan remain in this document.
- Add new entries here only for net-new scenarios not already covered.

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

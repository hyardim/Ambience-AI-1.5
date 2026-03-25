"""
Tests for:
  Sub-issue 1 — Admin metrics dashboard (GET /admin/stats)
  Sub-issue 3 — Privacy hardening (identifiers, not PII, in admin list views)
"""

# ---------------------------------------------------------------------------
# GET /admin/stats — sub-issue 1
# ---------------------------------------------------------------------------


class TestAdminStats:
    def test_stats_requires_auth(self, client):
        resp = client.get("/admin/stats")
        assert resp.status_code == 401

    def test_stats_requires_admin_role(self, client, gp_headers, specialist_headers):
        assert client.get("/admin/stats", headers=gp_headers).status_code == 403
        assert client.get("/admin/stats", headers=specialist_headers).status_code == 403

    def test_stats_response_structure(self, client, admin_headers):
        resp = client.get("/admin/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["total_ai_responses"], int)
        assert isinstance(data["rag_grounded_responses"], int)
        assert isinstance(data["specialist_responses"], int)
        assert isinstance(data["active_consultations"], int)
        assert isinstance(data["chats_by_status"], dict)
        assert isinstance(data["chats_by_specialty"], dict)
        assert isinstance(data["active_users_by_role"], dict)
        assert isinstance(data["daily_ai_queries"], list)

    def test_stats_zero_when_empty(self, client, admin_headers):
        resp = client.get("/admin/stats", headers=admin_headers)
        data = resp.json()
        assert data["total_ai_responses"] == 0
        assert data["rag_grounded_responses"] == 0
        assert data["specialist_responses"] == 0

    def test_stats_active_consultations_counts_open_chats(
        self, client, admin_headers, gp_headers
    ):
        client.post(
            "/chats/",
            json={"title": "Test Chat", "specialty": "neurology"},
            headers=gp_headers,
        )
        data = client.get("/admin/stats", headers=admin_headers).json()
        assert data["active_consultations"] >= 1

    def test_stats_chats_by_specialty_populated(
        self, client, admin_headers, gp_headers
    ):
        client.post(
            "/chats/",
            json={"title": "Neuro Chat", "specialty": "neurology"},
            headers=gp_headers,
        )
        data = client.get("/admin/stats", headers=admin_headers).json()
        assert data["chats_by_specialty"].get("neurology", 0) >= 1

    def test_stats_active_users_by_role(
        self, client, admin_headers, registered_gp, registered_specialist
    ):
        data = client.get("/admin/stats", headers=admin_headers).json()
        # admin + gp + specialist all registered
        assert data["active_users_by_role"].get("gp", 0) >= 1
        assert data["active_users_by_role"].get("specialist", 0) >= 1
        assert data["active_users_by_role"].get("admin", 0) >= 1

    def test_stats_daily_ai_queries_is_list_of_objects(self, client, admin_headers):
        data = client.get("/admin/stats", headers=admin_headers).json()
        for entry in data["daily_ai_queries"]:
            assert "date" in entry
            assert "count" in entry


# ---------------------------------------------------------------------------
# Privacy hardening — audit logs — sub-issue 3
# ---------------------------------------------------------------------------


class TestAuditLogPrivacy:
    def test_audit_log_has_user_identifier_field(
        self, client, admin_headers, registered_gp
    ):
        resp = client.get("/admin/logs", headers=admin_headers)
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) > 0
        for log in logs:
            assert "user_identifier" in log
            assert "user_email" not in log

    def test_audit_log_identifier_format_is_role_underscore_id(
        self, client, admin_headers, registered_gp
    ):
        resp = client.get("/admin/logs", headers=admin_headers)
        gp_logs = [
            log
            for log in resp.json()
            if log["user_identifier"] and log["user_identifier"].startswith("gp_")
        ]
        assert len(gp_logs) > 0
        for log in gp_logs:
            parts = log["user_identifier"].split("_")
            assert len(parts) == 2
            assert parts[1].isdigit()

    def test_audit_log_details_do_not_contain_email(
        self, client, admin_headers, registered_gp
    ):
        resp = client.get("/admin/logs", headers=admin_headers)
        for log in resp.json():
            if log.get("details"):
                assert "@" not in log["details"], (
                    f"Email leaked in audit details: {log['details']}"
                )

    def test_audit_log_has_category_field(self, client, admin_headers, registered_gp):
        resp = client.get("/admin/logs", headers=admin_headers)
        for log in resp.json():
            assert "category" in log
            assert log["category"] in ("AUTH", "CHAT", "SPECIALIST", "RAG", "OTHER")

    def test_audit_log_auth_actions_are_categorised_correctly(
        self, client, admin_headers, registered_gp
    ):
        resp = client.get("/admin/logs", headers=admin_headers)
        auth_logs = [
            log
            for log in resp.json()
            if log["action"] in ("REGISTER", "LOGIN", "LOGOUT")
        ]
        for log in auth_logs:
            assert log["category"] == "AUTH"


# ---------------------------------------------------------------------------
# Privacy hardening — admin chat list — sub-issue 3
# ---------------------------------------------------------------------------


class TestAdminChatListPrivacy:
    def test_chat_list_has_owner_identifier_not_name(
        self, client, admin_headers, gp_headers
    ):
        client.post(
            "/chats/",
            json={"title": "Test", "specialty": "neurology"},
            headers=gp_headers,
        )
        resp = client.get("/admin/chats", headers=admin_headers)
        assert resp.status_code == 200
        chats = resp.json()
        assert len(chats) > 0
        for chat in chats:
            assert "owner_identifier" in chat
            assert "owner_name" not in chat

    def test_owner_identifier_format_is_role_underscore_id(
        self, client, admin_headers, gp_headers
    ):
        client.post(
            "/chats/",
            json={"title": "Test", "specialty": "neurology"},
            headers=gp_headers,
        )
        resp = client.get("/admin/chats", headers=admin_headers)
        for chat in resp.json():
            if chat["owner_identifier"]:
                assert chat["owner_identifier"].startswith("gp_")
                assert "_" in chat["owner_identifier"]
                assert chat["owner_identifier"].split("_")[1].isdigit()

    def test_chat_list_has_specialist_identifier_not_name(
        self, client, admin_headers, gp_headers
    ):
        client.post(
            "/chats/",
            json={"title": "Test", "specialty": "neurology"},
            headers=gp_headers,
        )
        resp = client.get("/admin/chats", headers=admin_headers)
        for chat in resp.json():
            assert "specialist_identifier" in chat
            assert "specialist_name" not in chat

    def test_unassigned_chat_has_null_specialist_identifier(
        self, client, admin_headers, gp_headers
    ):
        client.post(
            "/chats/",
            json={"title": "Test", "specialty": "neurology"},
            headers=gp_headers,
        )
        resp = client.get("/admin/chats", headers=admin_headers)
        for chat in resp.json():
            if chat["specialist_id"] is None:
                assert chat["specialist_identifier"] is None

    def test_assigned_chat_has_specialist_identifier(
        self,
        client,
        admin_headers,
        gp_headers,
        specialist_headers,
        registered_specialist,
    ):
        # Create and submit a chat (sending a message auto-submits)
        chat = client.post(
            "/chats/",
            json={"title": "Test", "specialty": "neurology"},
            headers=gp_headers,
        ).json()
        client.post(
            f"/chats/{chat['id']}/message",
            json={"role": "user", "content": "Patient has wrist pain."},
            headers=gp_headers,
        )
        # Specialist self-assigns from the queue
        assign_resp = client.post(
            f"/specialist/chats/{chat['id']}/assign",
            json={"specialist_id": registered_specialist["user"]["id"]},
            headers=specialist_headers,
        )
        assert assign_resp.status_code == 200, assign_resp.text
        resp = client.get("/admin/chats", headers=admin_headers)
        assigned = next((c for c in resp.json() if c["id"] == chat["id"]), None)
        assert assigned is not None
        assert assigned["specialist_identifier"] is not None
        assert assigned["specialist_identifier"].startswith("specialist_")
        assert "specialist_name" not in assigned

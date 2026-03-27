"""
Tests for admin endpoints:
  GET    /admin/users
  GET    /admin/users/{id}
  PATCH  /admin/users/{id}
  DELETE /admin/users/{id}
  GET    /admin/chats
  GET    /admin/chats/{id}
  PATCH  /admin/chats/{id}
  DELETE /admin/chats/{id}
  GET    /admin/logs
  GET    /admin/rag/status
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# ---------------------------------------------------------------------------
# GET/PATCH/DELETE /admin/users
# ---------------------------------------------------------------------------


class TestAdminUsers:
    def test_list_users_returns_all(
        self, client, admin_headers, registered_gp, registered_specialist
    ):
        # admin + gp + specialist registered
        resp = client.get("/admin/users", headers=admin_headers)
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert registered_gp["user"]["email"] in emails
        assert registered_specialist["user"]["email"] in emails

    def test_list_users_filter_by_role(
        self, client, admin_headers, registered_gp, registered_specialist
    ):
        resp = client.get("/admin/users?role=gp", headers=admin_headers)
        assert resp.status_code == 200
        roles = {u["role"] for u in resp.json()}
        assert roles == {"gp"}

    def test_get_user_success(self, client, admin_headers, registered_gp):
        user_id = registered_gp["user"]["id"]
        resp = client.get(f"/admin/users/{user_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == user_id

    def test_get_user_not_found(self, client, admin_headers):
        resp = client.get("/admin/users/99999", headers=admin_headers)
        assert resp.status_code == 404

    def test_update_user_full_name(self, client, admin_headers, registered_gp):
        user_id = registered_gp["user"]["id"]
        resp = client.patch(
            f"/admin/users/{user_id}",
            json={"full_name": "Updated Name"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    def test_update_user_role(self, client, admin_headers, registered_gp):
        user_id = registered_gp["user"]["id"]
        resp = client.patch(
            f"/admin/users/{user_id}",
            json={"role": "specialist"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "specialist"

    def test_deactivate_user(self, client, admin_headers, registered_gp):
        user_id = registered_gp["user"]["id"]
        resp = client.delete(f"/admin/users/{user_id}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_non_admin_cannot_list_users(self, client, gp_headers):
        resp = client.get("/admin/users", headers=gp_headers)
        assert resp.status_code == 403

    def test_unauthenticated_cannot_list_users(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET/PATCH/DELETE /admin/chats
# ---------------------------------------------------------------------------


class TestAdminChats:
    def test_admin_sees_all_chats(self, client, admin_headers, created_chat):
        resp = client.get("/admin/chats", headers=admin_headers)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert created_chat["id"] in ids

    def test_admin_chat_has_owner_and_specialist_identifier_fields(
        self, client, admin_headers, created_chat
    ):
        resp = client.get("/admin/chats", headers=admin_headers)
        assert resp.status_code == 200
        chat = next(c for c in resp.json() if c["id"] == created_chat["id"])
        assert "owner_identifier" in chat
        assert "specialist_identifier" in chat

    def test_admin_get_chat_success(self, client, admin_headers, created_chat):
        resp = client.get(f"/admin/chats/{created_chat['id']}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == created_chat["id"]
        assert "messages" in resp.json()

    def test_admin_update_chat_title(self, client, admin_headers, created_chat):
        resp = client.patch(
            f"/admin/chats/{created_chat['id']}",
            json={"title": "Admin Updated Title"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Admin Updated Title"

    def test_admin_delete_chat(self, client, admin_headers, created_chat):
        resp = client.delete(
            f"/admin/chats/{created_chat['id']}", headers=admin_headers
        )
        assert resp.status_code == 204
        # Verify it's gone
        get_resp = client.get(
            f"/admin/chats/{created_chat['id']}", headers=admin_headers
        )
        assert get_resp.status_code == 404

    def test_non_admin_cannot_access_admin_chats(self, client, gp_headers):
        resp = client.get("/admin/chats", headers=gp_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/logs
# ---------------------------------------------------------------------------


class TestAdminLogs:
    def test_list_logs_returns_entries(self, client, admin_headers, registered_gp):
        # registered_gp triggers a REGISTER audit log entry
        resp = client.get("/admin/logs", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_list_logs_filter_by_action(self, client, admin_headers, registered_gp):
        resp = client.get("/admin/logs?action=REGISTER", headers=admin_headers)
        assert resp.status_code == 200
        actions = {log["action"] for log in resp.json()}
        assert actions == {"REGISTER"}

    def test_list_logs_filter_by_user_id(self, client, admin_headers, registered_gp):
        user_id = registered_gp["user"]["id"]
        resp = client.get(f"/admin/logs?user_id={user_id}", headers=admin_headers)
        assert resp.status_code == 200
        user_ids = {log["user_id"] for log in resp.json()}
        assert user_ids == {user_id}

    def test_non_admin_cannot_access_logs(self, client, gp_headers):
        resp = client.get("/admin/logs", headers=gp_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /admin/rag/status
# ---------------------------------------------------------------------------


class TestAdminRagStatus:
    def test_rag_status_success(self, client, admin_headers, monkeypatch):
        monkeypatch.setattr(
            "src.api.endpoints.admin.build_rag_headers",
            lambda: {"X-Internal-API-Key": "test-key"},
        )

        health_response = MagicMock()
        health_response.status_code = 200
        health_response.json.return_value = {"status": "healthy"}

        docs_response = MagicMock()
        docs_response.status_code = 200
        docs_response.json.return_value = [
            {"doc_id": "abc123", "source_name": "doc1.pdf", "chunk_count": 5},
        ]

        async_client_mock = AsyncMock()
        async_client_mock.get = AsyncMock(side_effect=[health_response, docs_response])
        async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
        async_client_mock.__aexit__ = AsyncMock(return_value=False)

        with patch.object(httpx, "AsyncClient", return_value=async_client_mock):
            resp = client.get("/admin/rag/status", headers=admin_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["service_status"] == "healthy"
        assert len(data["documents"]) == 1

    def test_rag_status_unavailable(self, client, admin_headers, monkeypatch):
        async_client_mock = AsyncMock()
        async_client_mock.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        async_client_mock.__aenter__ = AsyncMock(return_value=async_client_mock)
        async_client_mock.__aexit__ = AsyncMock(return_value=False)

        with patch.object(httpx, "AsyncClient", return_value=async_client_mock):
            resp = client.get("/admin/rag/status", headers=admin_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["service_status"] == "unavailable"
        assert data["documents"] == []

    def test_non_admin_cannot_access_rag_status(self, client, gp_headers):
        resp = client.get("/admin/rag/status", headers=gp_headers)
        assert resp.status_code == 403

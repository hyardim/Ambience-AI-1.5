"""
Tests for /chats endpoints: create, list, get, delete, and send message.
"""


# ---------------------------------------------------------------------------
# POST /chats/
# ---------------------------------------------------------------------------

class TestCreateChat:

    def test_create_chat_default_title(self, client, gp_headers):
        resp = client.post("/chats/", json={}, headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New Chat"
        assert "id" in data
        assert "user_id" in data
        assert "created_at" in data

    def test_create_chat_custom_title(self, client, gp_headers):
        resp = client.post("/chats/", json={"title": "Neurology Case"}, headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Neurology Case"

    def test_create_chat_unauthenticated_fails(self, client):
        resp = client.post("/chats/", json={"title": "No Auth"})
        assert resp.status_code == 401

    def test_create_chat_invalid_token_fails(self, client):
        resp = client.post("/chats/", json={}, headers={"Authorization": "Bearer bad.token"})
        assert resp.status_code == 401

    def test_create_multiple_chats(self, client, gp_headers):
        for i in range(3):
            resp = client.post("/chats/", json={"title": f"Chat {i}"}, headers=gp_headers)
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /chats/
# ---------------------------------------------------------------------------

class TestListChats:

    def test_list_chats_empty_for_new_user(self, client, gp_headers):
        resp = client.get("/chats/", headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_chats_returns_own_chats(self, client, gp_headers):
        client.post("/chats/", json={"title": "Chat A"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Chat B"}, headers=gp_headers)
        resp = client.get("/chats/", headers=gp_headers)
        assert resp.status_code == 200
        titles = [c["title"] for c in resp.json()]
        assert "Chat A" in titles
        assert "Chat B" in titles

    def test_list_chats_does_not_return_other_users_chats(
        self, client, gp_headers, second_gp_headers
    ):
        client.post("/chats/", json={"title": "Alice Chat"}, headers=gp_headers)
        resp = client.get("/chats/", headers=second_gp_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_chats_returns_all_chats(self, client, gp_headers):
        # Ordering by created_at DESC is unreliable in SQLite when inserts happen
        # within the same second. This test verifies all chats are returned.
        for title in ("First", "Second", "Third"):
            client.post("/chats/", json={"title": title}, headers=gp_headers)
        resp = client.get("/chats/", headers=gp_headers)
        assert resp.status_code == 200
        titles = {c["title"] for c in resp.json()}
        assert titles == {"First", "Second", "Third"}

    def test_list_chats_unauthenticated_fails(self, client):
        resp = client.get("/chats/")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /chats/{chat_id}
# ---------------------------------------------------------------------------

class TestGetChat:

    def test_get_chat_success(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == chat_id
        assert data["title"] == "Test Chat"

    def test_get_chat_not_found(self, client, gp_headers):
        resp = client.get("/chats/99999", headers=gp_headers)
        assert resp.status_code == 404

    def test_get_chat_belonging_to_other_user_fails(
        self, client, gp_headers, second_gp_headers, created_chat
    ):
        # created_chat belongs to gp_headers user; second_gp should not see it
        chat_id = created_chat["id"]
        resp = client.get(f"/chats/{chat_id}", headers=second_gp_headers)
        assert resp.status_code == 404

    def test_get_chat_unauthenticated_fails(self, client, created_chat):
        resp = client.get(f"/chats/{created_chat['id']}")
        assert resp.status_code == 401

    def test_get_chat_includes_messages(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": "Hello"},
            headers=gp_headers,
        )
        resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()["messages"]) >= 1


# ---------------------------------------------------------------------------
# DELETE /chats/{chat_id}
# ---------------------------------------------------------------------------

class TestDeleteChat:

    def test_delete_chat_success(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        resp = client.delete(f"/chats/{chat_id}", headers=gp_headers)
        assert resp.status_code == 204

    def test_delete_chat_is_gone_after_deletion(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        client.delete(f"/chats/{chat_id}", headers=gp_headers)
        resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        assert resp.status_code == 404

    def test_delete_chat_not_found(self, client, gp_headers):
        resp = client.delete("/chats/99999", headers=gp_headers)
        assert resp.status_code == 404

    def test_delete_chat_belonging_to_other_user_fails(
        self, client, gp_headers, second_gp_headers, created_chat
    ):
        chat_id = created_chat["id"]
        resp = client.delete(f"/chats/{chat_id}", headers=second_gp_headers)
        assert resp.status_code == 404
        # Verify original owner can still access it
        assert client.get(f"/chats/{chat_id}", headers=gp_headers).status_code == 200

    def test_delete_chat_unauthenticated_fails(self, client, created_chat):
        resp = client.delete(f"/chats/{created_chat['id']}")
        assert resp.status_code == 401

    def test_delete_chat_removes_messages(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": "Will be deleted"},
            headers=gp_headers,
        )
        client.delete(f"/chats/{chat_id}", headers=gp_headers)
        # Recreate a chat and verify no orphaned messages bleed over
        new_id = client.post("/chats/", json={"title": "Fresh"}, headers=gp_headers).json()["id"]
        get_resp = client.get(f"/chats/{new_id}", headers=gp_headers)
        assert get_resp.json()["messages"] == []


# ---------------------------------------------------------------------------
# POST /chats/{chat_id}/message
# ---------------------------------------------------------------------------

class TestSendMessage:

    def test_send_message_success(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        resp = client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": "What is rheumatoid arthritis?"},
            headers=gp_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "Message sent"
        assert "ai_response" in data

    def test_send_message_returns_mock_ai_response(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        content = "Tell me about neurology"
        resp = client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": content},
            headers=gp_headers,
        )
        assert resp.status_code == 200
        assert content in resp.json()["ai_response"]

    def test_send_message_persists_in_chat(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": "Persistent message"},
            headers=gp_headers,
        )
        chat_resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        messages = chat_resp.json()["messages"]
        contents = [m["content"] for m in messages]
        assert any("Persistent message" in c for c in contents)

    def test_send_message_to_nonexistent_chat_fails(self, client, gp_headers):
        resp = client.post(
            "/chats/99999/message",
            json={"role": "user", "content": "Hello"},
            headers=gp_headers,
        )
        assert resp.status_code == 404

    def test_send_message_to_other_users_chat_fails(
        self, client, gp_headers, second_gp_headers, created_chat
    ):
        chat_id = created_chat["id"]
        resp = client.post(
            f"/chats/{chat_id}/message",
            json={"role": "user", "content": "Intruder"},
            headers=second_gp_headers,
        )
        assert resp.status_code == 404

    def test_send_message_unauthenticated_fails(self, client, created_chat):
        resp = client.post(
            f"/chats/{created_chat['id']}/message",
            json={"role": "user", "content": "No auth"},
        )
        assert resp.status_code == 401

    def test_multiple_messages_accumulate(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        for i in range(3):
            client.post(
                f"/chats/{chat_id}/message",
                json={"role": "user", "content": f"Message {i}"},
                headers=gp_headers,
            )
        chat_resp = client.get(f"/chats/{chat_id}", headers=gp_headers)
        # Each user message gets an AI reply, so 3 messages → 6 total
        assert len(chat_resp.json()["messages"]) == 6

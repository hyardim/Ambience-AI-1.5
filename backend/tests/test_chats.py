"""
Tests for /chats endpoints: create, list, get, delete, and send message.
"""


# ---------------------------------------------------------------------------
# POST /chats/
# ---------------------------------------------------------------------------

class TestCreateChat:

    def test_create_chat_default_title(self, client, gp_headers):
        resp = client.post("/chats/", json={"specialty": "neurology"}, headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New Chat"
        assert "id" in data
        assert "user_id" in data
        assert "created_at" in data

    def test_create_chat_custom_title(self, client, gp_headers):
        resp = client.post("/chats/", json={"title": "Neurology Case", "specialty": "neurology"}, headers=gp_headers)
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
            resp = client.post("/chats/", json={"title": f"Chat {i}", "specialty": "neurology"}, headers=gp_headers)
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
        client.post("/chats/", json={"title": "Chat A", "specialty": "neurology"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Chat B", "specialty": "neurology"}, headers=gp_headers)
        resp = client.get("/chats/", headers=gp_headers)
        assert resp.status_code == 200
        titles = [c["title"] for c in resp.json()]
        assert "Chat A" in titles
        assert "Chat B" in titles

    def test_list_chats_does_not_return_other_users_chats(
        self, client, gp_headers, second_gp_headers
    ):
        client.post("/chats/", json={"title": "Alice Chat", "specialty": "neurology"}, headers=gp_headers)
        resp = client.get("/chats/", headers=second_gp_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_chats_returns_all_chats(self, client, gp_headers):
        # Ordering by created_at DESC is unreliable in SQLite when inserts happen
        # within the same second. This test verifies all chats are returned.
        for title in ("First", "Second", "Third"):
            client.post("/chats/", json={"title": title, "specialty": "neurology"}, headers=gp_headers)
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
        new_id = client.post("/chats/", json={"title": "Fresh", "specialty": "neurology"}, headers=gp_headers).json()["id"]
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

    def test_send_message_after_assignment_fails(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        # Assign specialist to the chat
        specialist_id = registered_specialist["user"]["id"]
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )
        # GP tries to send a message — should fail
        resp = client.post(
            f"/chats/{submitted_chat['id']}/message",
            json={"role": "user", "content": "More info"},
            headers=gp_headers,
        )
        assert resp.status_code == 400
        assert "assigned" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /chats/ — advanced filtering (search, specialty, date range)
# ---------------------------------------------------------------------------

class TestListChatsFiltering:

    def test_filter_by_specialty(self, client, gp_headers):
        client.post("/chats/", json={"title": "Neuro case", "specialty": "neurology"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Cardio case", "specialty": "cardiology"}, headers=gp_headers)

        resp = client.get("/chats/?specialty=neurology", headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["specialty"] == "neurology"

    def test_filter_by_search_text(self, client, gp_headers):
        client.post("/chats/", json={"title": "Headache assessment", "specialty": "neurology"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Joint pain", "specialty": "rheumatology"}, headers=gp_headers)

        resp = client.get("/chats/?search=headache", headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "Headache" in data[0]["title"]

    def test_search_is_case_insensitive(self, client, gp_headers):
        client.post("/chats/", json={"title": "Migraine Case", "specialty": "neurology"}, headers=gp_headers)

        resp = client.get("/chats/?search=MIGRAINE", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_search_partial_match(self, client, gp_headers):
        client.post("/chats/", json={"title": "Rheumatology follow-up", "specialty": "rheumatology"}, headers=gp_headers)

        resp = client.get("/chats/?search=follow", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_date_from(self, client, gp_headers):
        client.post("/chats/", json={"title": "Recent chat", "specialty": "neurology"}, headers=gp_headers)

        # Use a date far in the past — should include everything
        resp = client.get("/chats/?date_from=2000-01-01T00:00:00", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Use a date far in the future — should include nothing
        resp = client.get("/chats/?date_from=2099-01-01T00:00:00", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_filter_by_date_to(self, client, gp_headers):
        client.post("/chats/", json={"title": "Some chat", "specialty": "neurology"}, headers=gp_headers)

        # Date in the future — should include everything
        resp = client.get("/chats/?date_to=2099-12-31T23:59:59", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Date in the past — should include nothing
        resp = client.get("/chats/?date_to=2000-01-01T00:00:00", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_filter_by_date_range(self, client, gp_headers):
        client.post("/chats/", json={"title": "Today chat", "specialty": "neurology"}, headers=gp_headers)

        # Wide range — should include chat
        resp = client.get("/chats/?date_from=2000-01-01T00:00:00&date_to=2099-12-31T23:59:59", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_combined_search_and_specialty(self, client, gp_headers):
        client.post("/chats/", json={"title": "Headache neuro", "specialty": "neurology"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Headache cardio", "specialty": "cardiology"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Joint pain neuro", "specialty": "neurology"}, headers=gp_headers)

        resp = client.get("/chats/?search=headache&specialty=neurology", headers=gp_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Headache neuro"

    def test_combined_all_filters(self, client, gp_headers):
        client.post("/chats/", json={"title": "Full filter match", "specialty": "neurology"}, headers=gp_headers)
        client.post("/chats/", json={"title": "Wrong specialty", "specialty": "cardiology"}, headers=gp_headers)

        resp = client.get(
            "/chats/?search=full&specialty=neurology&date_from=2000-01-01T00:00:00&date_to=2099-12-31T23:59:59",
            headers=gp_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Full filter match"

    def test_invalid_date_from_returns_400(self, client, gp_headers):
        resp = client.get("/chats/?date_from=not-a-date", headers=gp_headers)
        assert resp.status_code == 400
        assert "date_from" in resp.json()["detail"]

    def test_invalid_date_to_returns_400(self, client, gp_headers):
        resp = client.get("/chats/?date_to=bad", headers=gp_headers)
        assert resp.status_code == 400
        assert "date_to" in resp.json()["detail"]

    def test_invalid_status_returns_400(self, client, gp_headers):
        resp = client.get("/chats/?status=nonexistent", headers=gp_headers)
        assert resp.status_code == 400

    def test_filter_by_status(self, client, gp_headers):
        client.post("/chats/", json={"title": "Open chat", "specialty": "neurology"}, headers=gp_headers)

        resp = client.get("/chats/?status=open", headers=gp_headers)
        assert resp.status_code == 200
        assert all(c["status"] == "open" for c in resp.json())

    def test_archived_chats_excluded_by_default(self, client, gp_headers):
        # Create a chat then archive it via update
        chat = client.post("/chats/", json={"title": "Will archive", "specialty": "neurology"}, headers=gp_headers).json()
        client.patch(f"/chats/{chat['id']}", json={"status": "archived"}, headers=gp_headers)

        resp = client.get("/chats/", headers=gp_headers)
        assert resp.status_code == 200
        assert all(c["status"] != "archived" for c in resp.json())

    def test_no_results_returns_empty_list(self, client, gp_headers):
        resp = client.get("/chats/?search=absolutelynothingmatches", headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json() == []

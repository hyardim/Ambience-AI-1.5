"""
Tests for PATCH /chats/{id} (update) and POST /chats/{id}/submit.
"""


# ---------------------------------------------------------------------------
# PATCH /chats/{chat_id}
# ---------------------------------------------------------------------------

class TestUpdateChat:

    def test_update_title_success(self, client, gp_headers, created_chat):
        resp = client.patch(
            f"/chats/{created_chat['id']}", json={"title": "Updated Title"}, headers=gp_headers
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_update_specialty_success(self, client, gp_headers, created_chat):
        resp = client.patch(
            f"/chats/{created_chat['id']}", json={"specialty": "cardiology"}, headers=gp_headers
        )
        assert resp.status_code == 200
        assert resp.json()["specialty"] == "cardiology"

    def test_update_chat_not_found(self, client, gp_headers):
        resp = client.patch("/chats/99999", json={"title": "Ghost"}, headers=gp_headers)
        assert resp.status_code == 404

    def test_update_other_users_chat_fails(self, client, second_gp_headers, created_chat):
        resp = client.patch(
            f"/chats/{created_chat['id']}", json={"title": "Hijack"}, headers=second_gp_headers
        )
        assert resp.status_code == 404

    def test_update_unauthenticated_fails(self, client, created_chat):
        resp = client.patch(f"/chats/{created_chat['id']}", json={"title": "No Auth"})
        assert resp.status_code == 401

    def test_update_after_assignment_fails(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        # Assign a specialist to the chat
        specialist_id = registered_specialist["user"]["id"]
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )
        # GP tries to update metadata — should be blocked
        resp = client.patch(
            f"/chats/{submitted_chat['id']}",
            json={"title": "Changed title"},
            headers=gp_headers,
        )
        assert resp.status_code == 400
        assert "specialist assignment" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /chats/{chat_id}/submit
# ---------------------------------------------------------------------------

class TestSubmitForReview:

    def test_submit_success(self, client, gp_headers, created_chat):
        resp = client.post(f"/chats/{created_chat['id']}/submit", headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    def test_submit_nonexistent_chat_fails(self, client, gp_headers):
        resp = client.post("/chats/99999/submit", headers=gp_headers)
        assert resp.status_code == 404

    def test_submit_other_users_chat_fails(self, client, second_gp_headers, created_chat):
        resp = client.post(f"/chats/{created_chat['id']}/submit", headers=second_gp_headers)
        assert resp.status_code == 404

    def test_submit_unauthenticated_fails(self, client, created_chat):
        resp = client.post(f"/chats/{created_chat['id']}/submit")
        assert resp.status_code == 401

    def test_resubmit_already_submitted_fails(self, client, gp_headers, created_chat):
        chat_id = created_chat["id"]
        client.post(f"/chats/{chat_id}/submit", headers=gp_headers)
        resp = client.post(f"/chats/{chat_id}/submit", headers=gp_headers)
        assert resp.status_code == 400
        assert "open" in resp.json()["detail"].lower()

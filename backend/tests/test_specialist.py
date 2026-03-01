"""
Tests for specialist endpoints:
  GET  /specialist/queue
  GET  /specialist/assigned
  GET  /specialist/chats/{id}
  POST /specialist/chats/{id}/assign
  POST /specialist/chats/{id}/review
  POST /specialist/chats/{id}/message
"""


# ---------------------------------------------------------------------------
# GET /specialist/queue
# ---------------------------------------------------------------------------


class TestSpecialistQueue:

    def test_queue_contains_submitted_chat(self, client, specialist_headers, submitted_chat):
        resp = client.get("/specialist/queue", headers=specialist_headers)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert submitted_chat["id"] in ids

    def test_queue_empty_before_any_submission(self, client, specialist_headers):
        resp = client.get("/specialist/queue", headers=specialist_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_queue_filtered_by_specialty(self, client, specialist_headers, gp_headers):
        # Create and submit a cardiology chat — neurology specialist should NOT see it
        cardio = client.post(
            "/chats/", json={"title": "Cardio Chat", "specialty": "cardiology"}, headers=gp_headers
        ).json()
        client.post(
            f"/chats/{cardio['id']}/message",
            json={"role": "user", "content": "Heart palpitations."},
            headers=gp_headers,
        )
        resp = client.get("/specialist/queue", headers=specialist_headers)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert cardio["id"] not in ids

    def test_gp_cannot_access_queue(self, client, gp_headers):
        resp = client.get("/specialist/queue", headers=gp_headers)
        assert resp.status_code == 403

    def test_unauthenticated_cannot_access_queue(self, client):
        resp = client.get("/specialist/queue")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /specialist/assigned
# ---------------------------------------------------------------------------


class TestSpecialistAssigned:

    def test_assigned_empty_before_assignment(self, client, specialist_headers):
        resp = client.get("/specialist/assigned", headers=specialist_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_assigned_contains_chat_after_assign(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )
        resp = client.get("/specialist/assigned", headers=specialist_headers)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert submitted_chat["id"] in ids


# ---------------------------------------------------------------------------
# GET /specialist/chats/{id}
# ---------------------------------------------------------------------------


class TestSpecialistChatDetail:

    def test_get_chat_detail_success(self, client, specialist_headers, submitted_chat):
        resp = client.get(f"/specialist/chats/{submitted_chat['id']}", headers=specialist_headers)
        assert resp.status_code == 200
        assert "messages" in resp.json()

    def test_get_chat_detail_not_found(self, client, specialist_headers):
        resp = client.get("/specialist/chats/99999", headers=specialist_headers)
        assert resp.status_code == 404

    def test_get_chat_outside_specialty_fails(self, client, specialist_headers, gp_headers):
        # Create and submit a cardiology chat
        cardio = client.post(
            "/chats/", json={"title": "Cardio", "specialty": "cardiology"}, headers=gp_headers
        ).json()
        client.post(
            f"/chats/{cardio['id']}/message",
            json={"role": "user", "content": "Chest pain."},
            headers=gp_headers,
        )
        # Neurology specialist should not be able to view it
        resp = client.get(f"/specialist/chats/{cardio['id']}", headers=specialist_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /specialist/chats/{id}/assign
# ---------------------------------------------------------------------------


class TestSpecialistAssign:

    def test_assign_success(self, client, specialist_headers, submitted_chat, registered_specialist):
        specialist_id = registered_specialist["user"]["id"]
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assigned"
        assert data["specialist_id"] == specialist_id

    def test_assign_removes_from_queue(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )
        queue = client.get("/specialist/queue", headers=specialist_headers).json()
        ids = [c["id"] for c in queue]
        assert submitted_chat["id"] not in ids

    def test_assign_not_submitted_fails(
        self, client, specialist_headers, created_chat, registered_specialist
    ):
        # created_chat is OPEN, not SUBMITTED
        resp = client.post(
            f"/specialist/chats/{created_chat['id']}/assign",
            json={"specialist_id": registered_specialist["user"]["id"]},
            headers=specialist_headers,
        )
        assert resp.status_code == 400

    def test_assign_nonexistent_chat_fails(self, client, specialist_headers, registered_specialist):
        resp = client.post(
            "/specialist/chats/99999/assign",
            json={"specialist_id": registered_specialist["user"]["id"]},
            headers=specialist_headers,
        )
        assert resp.status_code == 404

    def test_gp_cannot_assign(self, client, gp_headers, submitted_chat):
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/assign",
            json={"specialist_id": 1},
            headers=gp_headers,
        )
        assert resp.status_code == 403

    def test_assign_specialty_mismatch_fails(
        self, client, specialist_headers, gp_headers, registered_specialist
    ):
        # Create and submit a cardiology chat
        cardio = client.post(
            "/chats/", json={"title": "Cardio Chat", "specialty": "cardiology"}, headers=gp_headers
        ).json()
        client.post(
            f"/chats/{cardio['id']}/message",
            json={"role": "user", "content": "Heart palpitations."},
            headers=gp_headers,
        )
        # Neurology specialist should not be able to assign themselves
        resp = client.post(
            f"/specialist/chats/{cardio['id']}/assign",
            json={"specialist_id": registered_specialist["user"]["id"]},
            headers=specialist_headers,
        )
        assert resp.status_code == 403
        assert "specialty" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /specialist/chats/{id}/review
# ---------------------------------------------------------------------------


class TestSpecialistReview:

    def _assign(self, client, specialist_headers, chat_id, specialist_id):
        client.post(
            f"/specialist/chats/{chat_id}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )

    def test_review_approve_success(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "approve"},
            headers=specialist_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_review_reject_success(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "reject"},
            headers=specialist_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_review_with_feedback(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "reject", "feedback": "Needs MRI first"},
            headers=specialist_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["review_feedback"] == "Needs MRI first"

    def test_review_invalid_action_fails(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "maybe"},
            headers=specialist_headers,
        )
        assert resp.status_code == 400

    def test_review_unassigned_chat_fails(self, client, specialist_headers, submitted_chat):
        # Submitted but not yet assigned to anyone — review should fail
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "approve"},
            headers=specialist_headers,
        )
        assert resp.status_code == 404

    def test_gp_cannot_review(self, client, gp_headers, submitted_chat):
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "approve"},
            headers=gp_headers,
        )
        assert resp.status_code == 403

    def test_review_request_changes_keeps_reviewing(self, client, specialist_headers, submitted_chat, registered_specialist):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "request_changes", "feedback": "Add dosage details"},
            headers=specialist_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reviewing"
        assert data["review_feedback"] == "Add dosage details"

    def test_review_request_changes_regenerates_ai(self, client, specialist_headers, gp_headers, submitted_chat, registered_specialist):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        # Count messages before
        detail_before = client.get(f"/specialist/chats/{submitted_chat['id']}", headers=specialist_headers).json()
        msgs_before = len(detail_before["messages"])
        # Request changes
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "request_changes", "feedback": "Be more specific"},
            headers=specialist_headers,
        )
        # Verify a new AI message was appended
        detail_after = client.get(f"/specialist/chats/{submitted_chat['id']}", headers=specialist_headers).json()
        assert len(detail_after["messages"]) == msgs_before + 1
        new_msg = detail_after["messages"][-1]
        assert new_msg["sender"] == "ai"
        assert "Revised" in new_msg["content"]

    def test_review_request_changes_marks_old_ai_rejected(self, client, specialist_headers, submitted_chat, registered_specialist):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "request_changes", "feedback": "Wrong diagnosis"},
            headers=specialist_headers,
        )
        detail = client.get(f"/specialist/chats/{submitted_chat['id']}", headers=specialist_headers).json()
        ai_messages = [m for m in detail["messages"] if m["sender"] == "ai"]
        # The first (original) AI message should be marked rejected
        assert ai_messages[0]["review_status"] == "rejected"
        assert ai_messages[0]["review_feedback"] == "Wrong diagnosis"
        # The new AI message should have no review status yet
        assert ai_messages[-1]["review_status"] is None

    def test_review_request_changes_then_approve(self, client, specialist_headers, submitted_chat, registered_specialist):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        # First: request changes
        resp1 = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "request_changes", "feedback": "Add citations"},
            headers=specialist_headers,
        )
        assert resp1.json()["status"] == "reviewing"
        # Then: approve the revised response
        resp2 = client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "approve"},
            headers=specialist_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# POST /specialist/chats/{id}/message
# ---------------------------------------------------------------------------


class TestSpecialistMessage:

    def _assign(self, client, specialist_headers, chat_id, specialist_id):
        client.post(
            f"/specialist/chats/{chat_id}/assign",
            json={"specialist_id": specialist_id},
            headers=specialist_headers,
        )

    def test_specialist_message_success(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/message",
            json={"role": "specialist", "content": "Please get an MRI."},
            headers=specialist_headers,
        )
        assert resp.status_code == 200
        assert "message_id" in resp.json()

    def test_specialist_message_sets_reviewing(
        self, client, specialist_headers, submitted_chat, registered_specialist
    ):
        self._assign(client, specialist_headers, submitted_chat["id"], registered_specialist["user"]["id"])
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/message",
            json={"role": "specialist", "content": "Please clarify."},
            headers=specialist_headers,
        )
        detail = client.get(f"/specialist/chats/{submitted_chat['id']}", headers=specialist_headers).json()
        assert detail["status"] == "reviewing"

    def test_specialist_message_not_assigned_fails(self, client, specialist_headers, submitted_chat):
        # Not assigned to this specialist yet
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/message",
            json={"role": "specialist", "content": "Hello."},
            headers=specialist_headers,
        )
        assert resp.status_code == 404

    def test_gp_cannot_send_specialist_message(self, client, gp_headers, submitted_chat):
        resp = client.post(
            f"/specialist/chats/{submitted_chat['id']}/message",
            json={"role": "specialist", "content": "Pretending to be specialist."},
            headers=gp_headers,
        )
        assert resp.status_code == 403

"""
Tests for notification endpoints:
  GET   /notifications/
  PATCH /notifications/{id}/read
  PATCH /notifications/read-all

Notifications are triggered as a side-effect of specialist actions
(assign, approve, reject, message), so several tests exercise the full
specialist workflow to produce notifications for the GP user.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assign(client, specialist_headers, chat_id, specialist_id):
    """Assign the specialist to a submitted chat."""
    return client.post(
        f"/specialist/chats/{chat_id}/assign",
        json={"specialist_id": specialist_id},
        headers=specialist_headers,
    )


# ---------------------------------------------------------------------------
# GET /notifications/
# ---------------------------------------------------------------------------


class TestNotifications:

    def test_no_notifications_initially(self, client, gp_headers):
        resp = client.get("/notifications/", headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_notification_on_specialist_assign(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)

        resp = client.get("/notifications/", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["type"] == "chat_assigned"

    def test_notification_on_review_approve(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "approve"},
            headers=specialist_headers,
        )

        notif_types = [n["type"] for n in client.get("/notifications/", headers=gp_headers).json()]
        assert "chat_approved" in notif_types

    def test_notification_on_review_reject(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "reject", "feedback": "Needs more info"},
            headers=specialist_headers,
        )

        notif_types = [n["type"] for n in client.get("/notifications/", headers=gp_headers).json()]
        assert "chat_rejected" in notif_types

    def test_notification_on_request_changes(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/review",
            json={"action": "request_changes", "feedback": "More detail needed"},
            headers=specialist_headers,
        )

        notif_types = [n["type"] for n in client.get("/notifications/", headers=gp_headers).json()]
        assert "chat_revision" in notif_types

    def test_list_unread_only(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)

        # With unread_only=true, should see the new notification
        resp = client.get("/notifications/?unread_only=true", headers=gp_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Mark it read then unread_only should return empty
        notif_id = resp.json()[0]["id"]
        client.patch(f"/notifications/{notif_id}/read", headers=gp_headers)

        resp2 = client.get("/notifications/?unread_only=true", headers=gp_headers)
        assert resp2.json() == []

    def test_mark_notification_read(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)

        notifs = client.get("/notifications/", headers=gp_headers).json()
        notif_id = notifs[0]["id"]
        assert notifs[0]["is_read"] is False

        resp = client.patch(f"/notifications/{notif_id}/read", headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_mark_all_read(
        self, client, gp_headers, specialist_headers, submitted_chat, registered_specialist
    ):
        specialist_id = registered_specialist["user"]["id"]
        _assign(client, specialist_headers, submitted_chat["id"], specialist_id)
        # Send a message to trigger a second notification
        client.post(
            f"/specialist/chats/{submitted_chat['id']}/message",
            json={"role": "specialist", "content": "Please book an MRI."},
            headers=specialist_headers,
        )

        resp = client.patch("/notifications/read-all", headers=gp_headers)
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 2

        unread = client.get("/notifications/?unread_only=true", headers=gp_headers).json()
        assert unread == []

    def test_mark_nonexistent_notification_fails(self, client, gp_headers):
        resp = client.patch("/notifications/99999/read", headers=gp_headers)
        assert resp.status_code == 404

    def test_unauthenticated_cannot_list(self, client):
        resp = client.get("/notifications/")
        assert resp.status_code == 401

from __future__ import annotations

from src.db.models import ChatStatus, User


def test_cookie_auth_refresh_logout_flow(client, db_session, gp_user_payload):
    register = client.post("/auth/register", json=gp_user_payload)
    assert register.status_code == 201
    user = db_session.query(User).filter(User.email == gp_user_payload["email"]).first()
    assert user is not None
    initial_session_version = user.session_version

    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == gp_user_payload["email"]

    refresh = client.post("/auth/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["user"]["email"] == gp_user_payload["email"]

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"message": "Logged out successfully"}
    db_session.refresh(user)
    assert user.session_version == initial_session_version + 1

    me_after = client.get("/auth/me")
    assert me_after.status_code == 401

    refresh_after = client.post("/auth/refresh")
    assert refresh_after.status_code == 401


def test_gp_to_specialist_manual_response_flow(
    client,
    db_session,
    gp_user_payload,
    specialist_user_payload,
    monkeypatch,
):
    class _FakeRagResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": "AI draft recommendation", "citations_used": []}

    monkeypatch.setattr(
        "src.services.chat_service.httpx.post",
        lambda *args, **kwargs: _FakeRagResponse(),
    )

    gp_register = client.post("/auth/register", json=gp_user_payload)
    assert gp_register.status_code == 201
    gp_headers = {"Authorization": f"Bearer {gp_register.json()['access_token']}"}
    client.cookies.clear()

    specialist_register = client.post("/auth/register", json=specialist_user_payload)
    assert specialist_register.status_code == 201
    specialist = specialist_register.json()["user"]
    specialist_headers = {
        "Authorization": f"Bearer {specialist_register.json()['access_token']}"
    }
    client.cookies.clear()

    create_chat = client.post(
        "/chats/",
        json={"title": "MS relapse guidance", "specialty": "neurology"},
        headers=gp_headers,
    )
    assert create_chat.status_code == 200
    chat_id = create_chat.json()["id"]

    send_message = client.post(
        f"/chats/{chat_id}/message",
        json={"role": "user", "content": "Please review this AI draft."},
        headers=gp_headers,
    )
    assert send_message.status_code == 200

    assign = client.post(
        f"/specialist/chats/{chat_id}/assign",
        json={"specialist_id": specialist["id"]},
        headers=specialist_headers,
    )
    assert assign.status_code == 200
    assert assign.json()["status"] == "assigned"

    specialist_detail = client.get(
        f"/specialist/chats/{chat_id}",
        headers=specialist_headers,
    )
    assert specialist_detail.status_code == 200
    ai_message = next(
        (m for m in specialist_detail.json()["messages"] if m["sender"] == "ai"),
        None,
    )
    assert ai_message is not None

    review = client.post(
        f"/specialist/chats/{chat_id}/messages/{ai_message['id']}/review",
        json={
            "action": "manual_response",
            "replacement_content": "Specialist-confirmed answer",
            "replacement_sources": ["NICE CG186", "Local MS protocol"],
            "feedback": "Use specialist-approved wording",
        },
        headers=specialist_headers,
    )
    assert review.status_code == 200
    assert review.json()["status"] == "reviewing"

    detail = client.get(f"/chats/{chat_id}", headers=gp_headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data["status"] == "reviewing"

    specialist_messages = [m for m in data["messages"] if m["sender"] == "specialist"]
    assert len(specialist_messages) == 1
    assert specialist_messages[0]["content"] == "Specialist-confirmed answer"
    assert [c["title"] for c in specialist_messages[0]["citations"]] == [
        "NICE CG186",
        "Local MS protocol",
    ]

    reviewed_ai = next(
        (m for m in data["messages"] if m["id"] == ai_message["id"]), None
    )
    assert reviewed_ai is not None
    assert reviewed_ai["review_status"] == "replaced"
    assert reviewed_ai["review_feedback"] == "Use specialist-approved wording"


def _mock_rag_answer(monkeypatch, answer: str = "AI draft recommendation"):
    class _FakeRagResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": answer, "citations_used": []}

    monkeypatch.setattr(
        "src.services.chat_service.httpx.post",
        lambda *args, **kwargs: _FakeRagResponse(),
    )


def _mock_rag_revise(monkeypatch, answer: str = "Revised AI recommendation"):
    class _FakeRagResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": answer, "citations_used": []}

    monkeypatch.setattr(
        "src.services.specialist_review.httpx.post",
        lambda *args, **kwargs: _FakeRagResponse(),
    )


def _create_gp_chat(client, gp_headers, title="Clinical case", specialty="neurology"):
    created = client.post(
        "/chats/",
        json={"title": title, "specialty": specialty},
        headers=gp_headers,
    )
    assert created.status_code == 200
    return created.json()["id"]


def _send_gp_message(client, gp_headers, chat_id, content="Please advise"):
    sent = client.post(
        f"/chats/{chat_id}/message",
        json={"role": "user", "content": content},
        headers=gp_headers,
    )
    assert sent.status_code == 200


def _assign_to_specialist(client, specialist_headers, specialist_id, chat_id):
    assigned = client.post(
        f"/specialist/chats/{chat_id}/assign",
        json={"specialist_id": specialist_id},
        headers=specialist_headers,
    )
    assert assigned.status_code == 200
    return assigned


def test_full_chat_lifecycle_open_to_approved(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(client, gp_headers, title="Lifecycle approve")

    created = client.get(f"/chats/{chat_id}", headers=gp_headers)
    assert created.status_code == 200
    assert created.json()["status"] == ChatStatus.OPEN.value

    _send_gp_message(client, gp_headers, chat_id)
    submitted = client.get(f"/chats/{chat_id}", headers=gp_headers)
    assert submitted.status_code == 200
    assert submitted.json()["status"] == ChatStatus.SUBMITTED.value

    specialist_id = registered_specialist["user"]["id"]
    assigned = _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)
    assert assigned.json()["status"] == ChatStatus.ASSIGNED.value

    approved = client.post(
        f"/specialist/chats/{chat_id}/review",
        json={"action": "approve", "feedback": "Looks good"},
        headers=specialist_headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == ChatStatus.APPROVED.value
    assert approved.json()["reviewed_at"] is not None


def test_chat_lifecycle_reject_flow(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(client, gp_headers, title="Lifecycle reject")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)

    rejected = client.post(
        f"/specialist/chats/{chat_id}/review",
        json={"action": "reject", "feedback": "Insufficient evidence"},
        headers=specialist_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == ChatStatus.REJECTED.value
    assert rejected.json()["review_feedback"] == "Insufficient evidence"

    notifs = client.get("/notifications/?unread_only=true", headers=gp_headers)
    assert notifs.status_code == 200
    types = {n["type"] for n in notifs.json()}
    assert "chat_rejected" in types


def test_chat_lifecycle_request_changes_triggers_revision(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch, answer="Initial AI draft")
    _mock_rag_revise(monkeypatch, answer="Revised based on specialist feedback")

    chat_id = _create_gp_chat(client, gp_headers, title="Lifecycle request changes")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)

    revision = client.post(
        f"/specialist/chats/{chat_id}/review",
        json={"action": "request_changes", "feedback": "Add contraindications"},
        headers=specialist_headers,
    )
    assert revision.status_code == 200
    assert revision.json()["status"] == ChatStatus.REVIEWING.value

    detail = client.get(f"/chats/{chat_id}", headers=gp_headers)
    assert detail.status_code == 200
    ai_messages = [m for m in detail.json()["messages"] if m["sender"] == "ai"]
    assert any(
        "Revised based on specialist feedback" in m["content"] for m in ai_messages
    )
    assert any(m.get("review_status") == "rejected" for m in ai_messages)


def test_submit_only_open_chats(client, gp_headers):
    chat_id = _create_gp_chat(client, gp_headers, title="Submit once")
    first = client.post(f"/chats/{chat_id}/submit", headers=gp_headers)
    assert first.status_code == 200
    assert first.json()["status"] == ChatStatus.SUBMITTED.value

    second = client.post(f"/chats/{chat_id}/submit", headers=gp_headers)
    assert second.status_code == 400


def test_gp_cannot_edit_chat_after_assignment(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(client, gp_headers, title="Immutable after assign")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)

    updated = client.patch(
        f"/chats/{chat_id}",
        json={"title": "Should not update"},
        headers=gp_headers,
    )
    assert updated.status_code == 400


def test_specialist_per_message_approve(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(client, gp_headers, title="Per-message approve")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)

    specialist_detail = client.get(
        f"/specialist/chats/{chat_id}", headers=specialist_headers
    )
    ai_message = next(
        m for m in specialist_detail.json()["messages"] if m["sender"] == "ai"
    )

    reviewed = client.post(
        f"/specialist/chats/{chat_id}/messages/{ai_message['id']}/review",
        json={"action": "approve", "feedback": "Approved message"},
        headers=specialist_headers,
    )
    assert reviewed.status_code == 200

    detail = client.get(f"/chats/{chat_id}", headers=gp_headers).json()
    reviewed_message = next(
        m for m in detail["messages"] if m["id"] == ai_message["id"]
    )
    assert reviewed_message["review_status"] == "approved"


def test_specialist_per_message_request_changes(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch, answer="Original AI answer")
    _mock_rag_revise(monkeypatch, answer="Revised per-message AI answer")
    chat_id = _create_gp_chat(client, gp_headers, title="Per-message revise")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)

    specialist_detail = client.get(
        f"/specialist/chats/{chat_id}", headers=specialist_headers
    )
    ai_message = next(
        m for m in specialist_detail.json()["messages"] if m["sender"] == "ai"
    )

    reviewed = client.post(
        f"/specialist/chats/{chat_id}/messages/{ai_message['id']}/review",
        json={"action": "request_changes", "feedback": "Add risks"},
        headers=specialist_headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == ChatStatus.REVIEWING.value

    detail = client.get(f"/chats/{chat_id}", headers=gp_headers).json()
    assert any(m.get("review_status") == "rejected" for m in detail["messages"])
    assert any(
        m["sender"] == "ai" and "Revised per-message AI answer" in m["content"]
        for m in detail["messages"]
    )


def test_specialist_sends_message_transitions_to_reviewing(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(client, gp_headers, title="Specialist message")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)

    sent = client.post(
        f"/specialist/chats/{chat_id}/message",
        json={"role": "specialist", "content": "Please clarify symptom timeline."},
        headers=specialist_headers,
    )
    assert sent.status_code == 200

    detail = client.get(f"/chats/{chat_id}", headers=gp_headers).json()
    assert detail["status"] == ChatStatus.REVIEWING.value
    assert any(m["sender"] == "specialist" for m in detail["messages"])


def test_gp_cannot_see_other_gps_chats(client, gp_headers, second_gp_headers):
    chat_id = _create_gp_chat(client, gp_headers, title="Private chat")

    listed = client.get("/chats/", headers=second_gp_headers)
    assert listed.status_code == 200
    assert all(chat["id"] != chat_id for chat in listed.json())

    direct = client.get(f"/chats/{chat_id}", headers=second_gp_headers)
    assert direct.status_code == 404


def test_specialist_cannot_assign_wrong_specialty(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(
        client,
        gp_headers,
        title="Rheum case",
        specialty="rheumatology",
    )
    _send_gp_message(client, gp_headers, chat_id)

    specialist_id = registered_specialist["user"]["id"]
    assigned = client.post(
        f"/specialist/chats/{chat_id}/assign",
        json={"specialist_id": specialist_id},
        headers=specialist_headers,
    )
    assert assigned.status_code == 403


def test_role_based_endpoint_guards(client, gp_headers, specialist_headers):
    gp_to_specialist = client.get("/specialist/queue", headers=gp_headers)
    assert gp_to_specialist.status_code == 403

    gp_to_admin = client.get("/admin/stats", headers=gp_headers)
    assert gp_to_admin.status_code == 403

    specialist_to_admin = client.get("/admin/users", headers=specialist_headers)
    assert specialist_to_admin.status_code == 403


def test_notifications_created_on_assign_and_review(
    client,
    gp_headers,
    specialist_headers,
    registered_specialist,
    monkeypatch,
):
    _mock_rag_answer(monkeypatch)
    chat_id = _create_gp_chat(client, gp_headers, title="Notify flow")
    _send_gp_message(client, gp_headers, chat_id)
    specialist_id = registered_specialist["user"]["id"]
    _assign_to_specialist(client, specialist_headers, specialist_id, chat_id)
    client.post(
        f"/specialist/chats/{chat_id}/review",
        json={"action": "approve", "feedback": "Approved"},
        headers=specialist_headers,
    )

    unread = client.get("/notifications/?unread_only=true", headers=gp_headers)
    assert unread.status_code == 200
    types = [n["type"] for n in unread.json()]
    assert "chat_assigned" in types
    assert "chat_approved" in types

    unread_count = client.get("/notifications/unread-count", headers=gp_headers)
    assert unread_count.status_code == 200
    assert unread_count.json()["unread_count"] >= 2

    first_notif = unread.json()[0]
    marked = client.patch(
        f"/notifications/{first_notif['id']}/read",
        headers=gp_headers,
    )
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True

    mark_all = client.patch("/notifications/read-all", headers=gp_headers)
    assert mark_all.status_code == 200
    assert mark_all.json()["marked_read"] >= 1


def test_admin_stats_reflect_real_data(client, gp_headers, admin_headers):
    _create_gp_chat(client, gp_headers, title="Neuro case", specialty="neurology")
    _create_gp_chat(client, gp_headers, title="Rheum case", specialty="rheumatology")

    stats = client.get("/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    payload = stats.json()
    assert payload["chats_by_specialty"]["neurology"] >= 1
    assert payload["chats_by_specialty"]["rheumatology"] >= 1


def test_admin_deactivate_user_prevents_login(
    client,
    registered_gp,
    gp_user_payload,
    admin_headers,
):
    gp_id = registered_gp["user"]["id"]
    deactivated = client.delete(f"/admin/users/{gp_id}", headers=admin_headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    client.cookies.clear()
    login = client.post(
        "/auth/login",
        data={
            "username": gp_user_payload["email"],
            "password": gp_user_payload["password"],
        },
    )
    assert login.status_code == 400
    assert "deactivated" in login.json()["detail"].lower()


def test_admin_audit_logs_capture_actions(
    client,
    gp_headers,
    admin_headers,
):
    chat_id = _create_gp_chat(client, gp_headers, title="Audit target")
    submitted = client.post(f"/chats/{chat_id}/submit", headers=gp_headers)
    assert submitted.status_code == 200

    logs = client.get("/admin/logs", headers=admin_headers)
    assert logs.status_code == 200
    actions = {entry["action"] for entry in logs.json()}
    assert "CREATE_CHAT" in actions
    assert "SUBMIT_FOR_REVIEW" in actions

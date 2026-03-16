from __future__ import annotations

from src.db.models import Chat, Message, User


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
):
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

    submit = client.post(f"/chats/{chat_id}/submit", headers=gp_headers)
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"

    assign = client.post(
        f"/specialist/chats/{chat_id}/assign",
        json={"specialist_id": specialist["id"]},
        headers=specialist_headers,
    )
    assert assign.status_code == 200
    assert assign.json()["status"] == "assigned"

    chat = db_session.query(Chat).filter(Chat.id == chat_id).first()
    assert chat is not None
    ai_message = Message(
        chat_id=chat_id,
        content="AI draft recommendation",
        sender="ai",
    )
    db_session.add(ai_message)
    db_session.commit()
    db_session.refresh(ai_message)

    review = client.post(
        f"/specialist/chats/{chat_id}/messages/{ai_message.id}/review",
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

    refreshed_ai = db_session.query(Message).filter(Message.id == ai_message.id).first()
    assert refreshed_ai is not None
    assert refreshed_ai.review_status == "replaced"
    assert refreshed_ai.review_feedback == "Use specialist-approved wording"

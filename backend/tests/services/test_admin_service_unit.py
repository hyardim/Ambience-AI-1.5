from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from src.db.models import AuditLog, Chat, ChatStatus, Message, User, UserRole
from src.schemas.admin import UserUpdateAdmin
from src.schemas.chat import ChatUpdate
from src.services import admin_service


def _user(db_session, *, email: str, role: UserRole, specialty: str | None = None):
    user = User(
        email=email,
        hashed_password="hash",
        full_name=email,
        role=role,
        specialty=specialty,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _chat(db_session, owner: User, *, status: ChatStatus = ChatStatus.OPEN):
    chat = Chat(
        title="Chat",
        status=status,
        specialty="neurology",
        user_id=owner.id,
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    return chat


def test_list_users_rejects_invalid_role(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.list_users(db_session, role="ghost")
    assert exc.value.status_code == 400


def test_get_user_returns_cached_payload(monkeypatch, db_session):
    monkeypatch.setattr(
        admin_service.cache,
        "get_sync",
        lambda key, **kwargs: {
            "id": 99,
            "email": "cached@example.com",
            "full_name": "Cached",
            "role": "gp",
            "specialty": None,
            "is_active": True,
        },
    )
    response = admin_service.get_user(db_session, 99)
    assert response.email == "cached@example.com"


def test_get_user_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.get_user(db_session, 999)
    assert exc.value.status_code == 404


def test_update_user_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.update_user(db_session, 999, UserUpdateAdmin(full_name="X"))
    assert exc.value.status_code == 404


def test_update_user_rejects_invalid_role(db_session):
    user = _user(db_session, email="user@example.com", role=UserRole.GP)
    with pytest.raises(HTTPException) as exc:
        admin_service.update_user(
            db_session,
            user.id,
            UserUpdateAdmin(role="ghost"),
        )
    assert exc.value.status_code == 400


def test_update_user_updates_optional_fields(db_session):
    user = _user(db_session, email="user@example.com", role=UserRole.GP)
    updated = admin_service.update_user(
        db_session,
        user.id,
        UserUpdateAdmin(full_name="Updated", specialty="neurology", is_active=False),
    )
    assert updated.full_name == "Updated"
    assert updated.specialty == "neurology"
    assert updated.is_active is False


def test_deactivate_user_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.deactivate_user(db_session, 999)
    assert exc.value.status_code == 404


def test_list_all_chats_rejects_invalid_status(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.list_all_chats(db_session, status="ghost")
    assert exc.value.status_code == 400


def test_list_all_chats_returns_owner_and_specialist_identifiers(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, status=ChatStatus.REVIEWING)
    chat.specialist_id = specialist.id
    db_session.commit()
    result = admin_service.list_all_chats(
        db_session,
        status="reviewing",
        specialty="neurology",
        user_id=owner.id,
        specialist_id=specialist.id,
    )
    assert result[0]["owner_identifier"] == f"gp_{owner.id}"
    assert result[0]["specialist_identifier"] == f"specialist_{specialist.id}"


def test_get_any_chat_returns_cached_payload(monkeypatch, db_session):
    monkeypatch.setattr(
        admin_service.cache,
        "get_sync",
        lambda key, **kwargs: {
            "id": 1,
            "title": "Cached",
            "status": "open",
            "specialty": "neurology",
            "severity": None,
            "patient_age": None,
            "patient_gender": None,
            "patient_notes": None,
            "specialist_id": None,
            "assigned_at": None,
            "reviewed_at": None,
            "review_feedback": None,
            "created_at": "2024-01-01T00:00:00",
            "user_id": 1,
            "messages": [],
            "files": [],
        },
    )
    response = admin_service.get_any_chat(db_session, 1)
    assert response.title == "Cached"


def test_get_any_chat_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.get_any_chat(db_session, 999)
    assert exc.value.status_code == 404


def test_update_any_chat_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.update_any_chat(db_session, 999, ChatUpdate(title="X"))
    assert exc.value.status_code == 404


def test_update_any_chat_rejects_invalid_status(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    chat = _chat(db_session, owner)
    with pytest.raises(HTTPException) as exc:
        admin_service.update_any_chat(db_session, chat.id, ChatUpdate(status="ghost"))
    assert exc.value.status_code == 400


def test_update_any_chat_updates_optional_fields(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    chat = _chat(db_session, owner)
    updated = admin_service.update_any_chat(
        db_session,
        chat.id,
        ChatUpdate(title="Updated", specialty="rheumatology", severity="high"),
    )
    assert updated["title"] == "Updated"
    assert updated["specialty"] == "rheumatology"
    assert updated["severity"] == "high"
    assert updated["owner_identifier"] == f"gp_{owner.id}"
    assert updated["specialist_identifier"] is None


def test_delete_any_chat_not_found(db_session):
    with pytest.raises(HTTPException) as exc:
        admin_service.delete_any_chat(db_session, 999)
    assert exc.value.status_code == 404


def test_action_category_falls_back_to_other():
    assert admin_service._action_category("SOMETHING_NEW") == "OTHER"


def test_list_audit_logs_filters_by_category_action_user_dates_and_search(db_session):
    user = _user(db_session, email="gp@example.com", role=UserRole.GP)
    old_log = AuditLog(
        user_id=user.id,
        action="LOGIN",
        details="old login",
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    new_log = AuditLog(
        user_id=user.id,
        action="RAG_ANSWER",
        details="latest query",
        timestamp=datetime(2024, 2, 1, tzinfo=timezone.utc),
    )
    db_session.add_all([old_log, new_log])
    db_session.commit()

    result = admin_service.list_audit_logs(
        db_session,
        action="rag_answer",
        category="rag",
        search="latest",
        user_id=user.id,
        date_from=datetime(2024, 1, 15, tzinfo=timezone.utc),
        date_to=datetime(2024, 2, 15, tzinfo=timezone.utc),
        limit=5,
    )
    assert len(result) == 1
    assert result[0]["category"] == "RAG"


def test_get_stats_counts_truthy_citations_only(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    chat = _chat(db_session, owner, status=ChatStatus.OPEN)
    db_session.add_all(
        [
            Message(chat_id=chat.id, content="a", sender="ai", citations=[]),
            Message(chat_id=chat.id, content="b", sender="ai", citations=[{"x": 1}]),
            Message(chat_id=chat.id, content="c", sender="specialist"),
        ]
    )
    db_session.commit()

    stats = admin_service.get_stats(db_session)
    assert stats["total_ai_responses"] == 2
    assert stats["rag_grounded_responses"] == 1
    assert stats["specialist_responses"] == 1

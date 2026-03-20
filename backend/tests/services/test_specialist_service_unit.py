from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.db.models import Chat, ChatStatus, Message, User, UserRole
from src.schemas.chat import ReviewRequest
from src.services import (
    cache_invalidation,
    specialist_review,
    specialist_service,
)


def _user(
    db_session,
    *,
    email: str,
    role: UserRole,
    specialty: str | None = None,
) -> User:
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


def _chat(
    db_session, owner: User, specialist: User | None = None, *, status: ChatStatus
):
    chat = Chat(
        title="Chat",
        status=status,
        specialty="neurology",
        user_id=owner.id,
        specialist_id=specialist.id if specialist else None,
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    return chat


def _ai_message(db_session, chat: Chat) -> Message:
    msg = Message(chat_id=chat.id, content="AI content", sender="ai")
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)
    return msg


def test_build_manual_citations_handles_empty_sources():
    assert specialist_service._build_manual_citations(None) is None
    assert specialist_service._build_manual_citations(["", "  "]) is None


def test_specialist_service_reexports_expected_helpers():
    assert specialist_service.assign is not None
    assert specialist_service.review is not None
    assert specialist_service.send_message is not None
    assert specialist_service._invalidate_admin_chat_caches is not None
    assert specialist_service._invalidate_admin_stats_cache is not None
    assert specialist_service._invalidate_specialist_lists is not None
    assert specialist_service.cache is not None


def test_get_queue_uses_cache(monkeypatch, db_session):
    monkeypatch.setattr(
        specialist_service.cache,
        "get_sync",
        lambda *args, **kwargs: [
            {
                "id": 1,
                "title": "Cached",
                "status": "submitted",
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
            }
        ],
    )
    specialist = SimpleNamespace(id=1, specialty="neurology")
    result = specialist_service.get_queue(db_session, specialist)
    assert result[0].title == "Cached"


def test_get_assigned_uses_cache(monkeypatch, db_session):
    monkeypatch.setattr(
        specialist_service.cache,
        "get_sync",
        lambda *args, **kwargs: [
            {
                "id": 1,
                "title": "Cached",
                "status": "assigned",
                "specialty": "neurology",
                "severity": None,
                "patient_age": None,
                "patient_gender": None,
                "patient_notes": None,
                "specialist_id": 2,
                "assigned_at": None,
                "reviewed_at": None,
                "review_feedback": None,
                "created_at": "2024-01-01T00:00:00",
                "user_id": 1,
            }
        ],
    )
    specialist = SimpleNamespace(id=2)
    result = specialist_service.get_assigned(db_session, specialist)
    assert result[0].status == "assigned"


def test_get_chat_detail_uses_cache(monkeypatch, db_session):
    monkeypatch.setattr(
        specialist_service.cache,
        "get_sync",
        lambda *args, **kwargs: {
            "id": 1,
            "title": "Cached",
            "status": "reviewing",
            "specialty": "neurology",
            "severity": None,
            "patient_age": None,
            "patient_gender": None,
            "patient_notes": None,
            "specialist_id": 2,
            "assigned_at": None,
            "reviewed_at": None,
            "review_feedback": None,
            "created_at": "2024-01-01T00:00:00",
            "user_id": 1,
            "messages": [],
            "files": [],
        },
    )
    specialist = SimpleNamespace(id=2)
    result = specialist_service.get_chat_detail(db_session, specialist, 1)
    assert result.title == "Cached"


def test_invalidate_specialist_lists_without_specialist_id(monkeypatch):
    deleted = []
    patterns = []
    monkeypatch.setattr(
        cache_invalidation.cache,
        "delete_sync",
        lambda *args, **kwargs: deleted.append(args),
    )
    monkeypatch.setattr(
        cache_invalidation.cache,
        "delete_pattern_sync",
        lambda *args, **kwargs: patterns.append(args),
    )
    cache_invalidation.invalidate_specialist_lists_sync(
        specialty=None,
        specialist_id=None,
    )
    assert deleted == []
    assert patterns


def test_review_rejects_invalid_action(db_session):
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    with pytest.raises(HTTPException) as exc:
        specialist_service.review(
            db_session, specialist, 1, ReviewRequest(action="manual_response")
        )
    assert exc.value.status_code == 400


def test_review_rejects_invalid_status(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.APPROVED)
    with pytest.raises(HTTPException) as exc:
        specialist_service.review(
            db_session, specialist, chat.id, ReviewRequest(action="approve")
        )
    assert exc.value.status_code == 400


def test_assign_rejects_assigning_other_specialist(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, status=ChatStatus.SUBMITTED)
    with pytest.raises(HTTPException) as exc:
        specialist_service.assign(
            db_session,
            specialist,
            chat.id,
            SimpleNamespace(specialist_id=specialist.id + 1),
        )
    assert exc.value.status_code == 403


def test_review_blocks_terminal_actions_while_generation_in_progress(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)
    db_session.add(
        Message(chat_id=chat.id, content="", sender="ai", is_generating=True)
    )
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        specialist_service.review(
            db_session, specialist, chat.id, ReviewRequest(action="approve")
        )
    assert exc.value.status_code == 400


def test_review_message_rejects_missing_manual_response_content(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    ai_message = _ai_message(db_session, chat)
    with pytest.raises(HTTPException) as exc:
        specialist_service.review_message(
            db_session,
            specialist,
            chat.id,
            ai_message.id,
            ReviewRequest(action="manual_response", replacement_content="  "),
        )
    assert exc.value.status_code == 400


def test_review_message_rejects_none_manual_response_content(db_session):
    owner = _user(db_session, email="gp2@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec2@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    ai_message = _ai_message(db_session, chat)
    with pytest.raises(HTTPException) as exc:
        specialist_service.review_message(
            db_session,
            specialist,
            chat.id,
            ai_message.id,
            ReviewRequest(action="manual_response"),
        )
    assert exc.value.status_code == 400


def test_review_message_accepts_trimmed_manual_response_content(db_session):
    owner = _user(db_session, email="gp-trim@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec-trim@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    ai_message = _ai_message(db_session, chat)

    response = specialist_service.review_message(
        db_session,
        specialist,
        chat.id,
        ai_message.id,
        ReviewRequest(
            action="manual_response",
            replacement_content="  Use this instead  ",
            replacement_sources=["NICE"],
        ),
    )

    specialist_msg = (
        db_session.query(Message)
        .filter(Message.chat_id == chat.id, Message.sender == "specialist")
        .order_by(Message.id.desc())
        .first()
    )
    assert specialist_msg is not None
    assert specialist_msg.content == "Use this instead"
    assert response.status == ChatStatus.REVIEWING.value

    with pytest.raises(HTTPException) as direct_exc:
        specialist_review.review_message(
            db_session,
            specialist,
            chat.id,
            ai_message.id,
            ReviewRequest(action="manual_response"),
        )
    assert direct_exc.value.status_code == 400


def test_review_message_manual_response_creates_specialist_message(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)
    ai_message = _ai_message(db_session, chat)

    response = specialist_service.review_message(
        db_session,
        specialist,
        chat.id,
        ai_message.id,
        ReviewRequest(
            action="manual_response",
            replacement_content="Manual specialist answer",
            replacement_sources=["NICE CG123", " "],
        ),
    )

    specialist_messages = (
        db_session.query(Message)
        .filter(Message.chat_id == chat.id, Message.sender == "specialist")
        .all()
    )
    assert response.status == "reviewing"
    assert len(specialist_messages) == 1
    assert specialist_messages[0].citations[0]["title"] == "NICE CG123"


def test_review_message_request_changes_path(monkeypatch, db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)
    ai_message = _ai_message(db_session, chat)
    called = []
    monkeypatch.setattr(
        specialist_review,
        "_regenerate_ai_response",
        lambda db, current_chat, feedback: called.append(feedback),
    )
    response = specialist_service.review_message(
        db_session,
        specialist,
        chat.id,
        ai_message.id,
        ReviewRequest(action="request_changes", feedback="Needs work"),
    )
    assert response.status == "reviewing"
    assert called == ["Needs work"]


def test_review_message_rejects_invalid_action(db_session):
    _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    with pytest.raises(ValidationError):
        ReviewRequest(action="ghost")


def test_review_message_rejects_missing_chat(db_session):
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    with pytest.raises(HTTPException) as exc:
        specialist_service.review_message(
            db_session, specialist, 1, 1, ReviewRequest(action="approve")
        )
    assert exc.value.status_code == 404


def test_review_message_rejects_invalid_chat_status(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.APPROVED)
    with pytest.raises(HTTPException) as exc:
        specialist_service.review_message(
            db_session, specialist, chat.id, 1, ReviewRequest(action="approve")
        )
    assert exc.value.status_code == 400


def test_review_message_rejects_missing_ai_message(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    with pytest.raises(HTTPException) as exc:
        specialist_service.review_message(
            db_session, specialist, chat.id, 999, ReviewRequest(action="approve")
        )
    assert exc.value.status_code == 404


def test_mark_last_ai_message_noop_when_none_pending(db_session):
    specialist_review._mark_last_ai_message(
        db_session, 999, ReviewRequest(action="approve")
    )


def test_regenerate_ai_response_uses_sync_path_when_inline_ai_enabled(
    monkeypatch, db_session
):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    db_session.add_all(
        [
            Message(chat_id=chat.id, content="User asks", sender="user"),
            Message(chat_id=chat.id, content="Old answer", sender="ai"),
        ]
    )
    db_session.commit()

    called = {}

    def fake_do_revise(*args):
        called["args"] = args

    monkeypatch.setattr(specialist_review.settings, "INLINE_AI_TASKS", True)
    monkeypatch.setattr(specialist_review, "_do_revise", fake_do_revise)
    placeholder = specialist_review._regenerate_ai_response(
        db_session, chat, "feedback"
    )
    assert placeholder.is_generating is True
    assert called["args"][2] == "User asks"
    assert called["args"][3] == "Old answer"


def test_regenerate_ai_response_handles_empty_context(monkeypatch):
    fake_db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )
    fake_chat = SimpleNamespace(
        id=11,
        specialty=None,
        severity=None,
        patient_context=None,
        files=[
            SimpleNamespace(
                filename="doc.txt", file_path="/tmp/doc.txt", file_type="text/plain"
            )
        ],
    )
    called = {}
    monkeypatch.setattr(
        specialist_review.message_repository,
        "list_for_chat",
        lambda db, chat_id: [],
    )
    monkeypatch.setattr(
        specialist_review.message_repository,
        "create",
        lambda *args, **kwargs: SimpleNamespace(id=7, is_generating=True),
    )
    monkeypatch.setattr(specialist_review, "_extract_text", lambda *args: "x" * 9000)

    def fake_do_revise(*args):
        called["args"] = args

    monkeypatch.setattr(specialist_review, "_do_revise", fake_do_revise)
    specialist_review._regenerate_ai_response(fake_db, fake_chat, "feedback")
    assert called["args"][2] == "consultation"
    assert called["args"][6] is None
    assert called["args"][7] is None
    assert called["args"][8].endswith("[Document truncated to fit context window]")
    assert called["args"][9] is True


def test_regenerate_ai_response_still_calls_revise_when_inline_ai_disabled(
    monkeypatch, db_session
):
    fake_db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    fake_chat = SimpleNamespace(
        id=11,
        specialty="neurology",
        severity=None,
        patient_context=None,
        files=[],
    )
    monkeypatch.setattr(
        specialist_review.message_repository,
        "list_for_chat",
        lambda db, chat_id: [SimpleNamespace(sender="user", content="User asks")],
    )
    monkeypatch.setattr(
        specialist_review.message_repository,
        "create",
        lambda *args, **kwargs: SimpleNamespace(id=7, is_generating=True),
    )
    called = {}

    def fake_do_revise(*args):
        called["args"] = args

    monkeypatch.setattr(specialist_review.settings, "INLINE_AI_TASKS", False)
    monkeypatch.setattr(specialist_review, "_do_revise", fake_do_revise)
    specialist_review._regenerate_ai_response(fake_db, fake_chat, "feedback")

    assert called["args"][2] == "User asks"
    assert called["args"][3] == ""
    assert called["args"][4] == "feedback"


def test_do_revise_updates_placeholder_and_handles_audit_failure(
    monkeypatch, db_session
):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    placeholder = Message(
        chat_id=chat.id, content="old", sender="ai", is_generating=True
    )
    db_session.add(placeholder)
    db_session.commit()
    db_session.refresh(placeholder)

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "answer": "revised",
        "citations_used": [{"title": "Doc"}],
    }
    monkeypatch.setattr(
        specialist_review.httpx, "post", lambda *args, **kwargs: response
    )
    monkeypatch.setattr(
        specialist_review.audit_repository,
        "log",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit fail")),
    )

    specialist_review._do_revise(
        db_session,
        placeholder,
        "question",
        "old answer",
        "feedback",
        "neurology",
        None,
        None,
        None,
        False,
    )

    db_session.refresh(placeholder)
    assert placeholder.content == "revised"
    assert placeholder.is_generating is False


def test_do_revise_invalidates_admin_caches_when_chat_missing(monkeypatch):
    placeholder = SimpleNamespace(
        chat_id=5,
        content="",
        citations=None,
        is_generating=True,
    )

    class FakeDB:
        def commit(self):
            return None

        def refresh(self, obj):
            return None

        def query(self, model):
            return SimpleNamespace(
                filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: None)
            )

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "answer": "revised",
        "citations_used": [{"title": "Doc"}],
    }
    invalidations = []

    monkeypatch.setattr(
        specialist_review.httpx, "post", lambda *args, **kwargs: response
    )
    monkeypatch.setattr(
        specialist_review,
        "_invalidate_admin_chat_caches",
        lambda chat_id: invalidations.append(("chat", chat_id)),
    )
    monkeypatch.setattr(
        specialist_review,
        "_invalidate_admin_stats_cache",
        lambda: invalidations.append(("stats", None)),
    )
    monkeypatch.setattr(
        specialist_review.audit_repository,
        "log",
        lambda *args, **kwargs: None,
    )

    specialist_review._do_revise(
        FakeDB(),
        placeholder,
        "question",
        "old answer",
        "feedback",
        "neurology",
        None,
        None,
        None,
        False,
    )

    assert invalidations == [("chat", 5), ("stats", None)]


def test_do_revise_failure_logs_rag_error_and_notifies_user(monkeypatch, db_session):
    owner = _user(db_session, email="gp2@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec2@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    placeholder = Message(
        chat_id=chat.id, content="old", sender="ai", is_generating=True
    )
    db_session.add(placeholder)
    db_session.commit()
    db_session.refresh(placeholder)

    audit_actions = []
    notifications = []
    invalidated = []

    def fail_post(*args, **kwargs):
        raise RuntimeError("rag down")

    monkeypatch.setattr(specialist_review.httpx, "post", fail_post)
    monkeypatch.setattr(
        specialist_review.audit_repository,
        "log",
        lambda *_args, **kwargs: audit_actions.append(kwargs.get("action")),
    )
    monkeypatch.setattr(
        specialist_review.notification_repository,
        "create",
        lambda *_args, **kwargs: notifications.append(kwargs),
    )
    monkeypatch.setattr(
        specialist_review,
        "invalidate_notification_caches",
        lambda user_id: invalidated.append(user_id),
    )

    specialist_review._do_revise(
        db_session,
        placeholder,
        "question",
        "old answer",
        "feedback",
        "neurology",
        None,
        None,
        None,
        False,
    )

    db_session.refresh(placeholder)
    assert "temporarily unavailable" in placeholder.content
    assert audit_actions[-1] == "RAG_ERROR"
    assert notifications[-1]["user_id"] == owner.id
    assert notifications[-1]["chat_id"] == chat.id
    assert invalidated == [owner.id]


def test_regenerate_ai_response_task_returns_when_placeholder_missing(monkeypatch):
    fake_db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: None)
        ),
        rollback=lambda: None,
        close=lambda: None,
    )
    monkeypatch.setattr(specialist_review, "SessionLocal", lambda: fake_db)
    closed = []
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
        lambda chat_id: closed.append(chat_id),
    )
    specialist_review._regenerate_ai_response_task(1, 9, "q", "a", "f", None, None)
    assert closed == [9]


def test_regenerate_ai_response_task_streams_and_finalises(monkeypatch):
    placeholder = SimpleNamespace(
        id=3,
        chat_id=5,
        content="",
        citations=None,
        is_generating=True,
    )
    chat = SimpleNamespace(
        id=5,
        user_id=7,
        specialist_id=11,
        specialty="neurology",
        severity=None,
        patient_context=None,
        files=[
            SimpleNamespace(
                filename="doc.txt",
                file_path="/tmp/doc.txt",
                file_type="text/plain",
            )
        ],
    )
    messages = [SimpleNamespace(sender="user", content="Question")]

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            if self.model is Message:
                return placeholder
            return chat

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

        def commit(self):
            return None

        def refresh(self, obj):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield ""
            yield '{"type":"chunk","delta":"Hi"}'
            yield "not-json"
            yield '{"type":"done","answer":"Hello","citations":[{"title":"Doc"}]}'

    class FakeClient:
        def __init__(self, timeout):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json):
            class Ctx:
                def __enter__(self_inner):
                    return FakeResponse()

                def __exit__(self_inner, exc_type, exc, tb):
                    return None

            return Ctx()

    published = []
    monkeypatch.setattr(specialist_review, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        specialist_review.message_repository,
        "list_for_chat",
        lambda db, chat_id: messages,
    )
    monkeypatch.setattr(specialist_review, "_extract_text", lambda *args: "x" * 9000)
    monkeypatch.setattr(specialist_review.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda chat_id, event: published.append(event.event),
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
        lambda chat_id: published.append("closed"),
    )

    specialist_review._regenerate_ai_response_task(
        3, 5, "Q", "A", "F", "neurology", None
    )

    assert placeholder.content == "Hello"
    assert placeholder.citations == [{"title": "Doc"}]
    assert placeholder.is_generating is False
    assert published[0] == "stream_start"
    assert "complete" in published
    assert published[-1] == "closed"


def test_regenerate_ai_response_task_invalidates_admin_caches_when_chat_missing(
    monkeypatch,
):
    placeholder = SimpleNamespace(
        id=3,
        chat_id=5,
        content="",
        citations=None,
        is_generating=True,
    )

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            if self.model is Message:
                return placeholder
            return None

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

        def commit(self):
            return None

        def refresh(self, obj):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield '{"type":"done","answer":"Hello","citations":[{"title":"Doc"}]}'

    class FakeClient:
        def __init__(self, timeout):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json):
            class Ctx:
                def __enter__(self_inner):
                    return FakeResponse()

                def __exit__(self_inner, exc_type, exc, tb):
                    return None

            return Ctx()

    invalidations = []
    monkeypatch.setattr(specialist_review, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(specialist_review.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        specialist_review,
        "_invalidate_admin_chat_caches",
        lambda chat_id: invalidations.append(("chat", chat_id)),
    )
    monkeypatch.setattr(
        specialist_review,
        "_invalidate_admin_stats_cache",
        lambda: invalidations.append(("stats", None)),
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda chat_id, event: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
        lambda chat_id: None,
    )

    specialist_review._regenerate_ai_response_task(3, 5, "Q", "A", "F", None, None)

    assert placeholder.content == "Hello"
    assert invalidations == [("chat", 5), ("stats", None)]


def test_regenerate_ai_response_task_stream_error_falls_back(monkeypatch):
    placeholder = SimpleNamespace(
        id=3,
        chat_id=5,
        content="",
        citations=None,
        is_generating=True,
    )
    chat = SimpleNamespace(
        id=5,
        user_id=7,
        specialist_id=11,
        specialty=None,
        severity=None,
        patient_context=None,
        files=[],
    )

    class FakeQuery:
        def __init__(self, model):
            self.model = model

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            if self.model is Message:
                return placeholder
            return chat

    class FakeDB:
        def query(self, model):
            return FakeQuery(model)

        def commit(self):
            return None

        def refresh(self, obj):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield '{"type":"error","error":"bad stream"}'

    class FakeClient:
        def __init__(self, timeout):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json):
            class Ctx:
                def __enter__(self_inner):
                    return FakeResponse()

                def __exit__(self_inner, exc_type, exc, tb):
                    return None

            return Ctx()

    monkeypatch.setattr(specialist_review, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        specialist_review.message_repository,
        "list_for_chat",
        lambda db, chat_id: [],
    )
    monkeypatch.setattr(specialist_review.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda chat_id, event: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
        lambda chat_id: None,
    )

    specialist_review._regenerate_ai_response_task(3, 5, "Q", "A", "F", None, None)
    assert (
        "clinical knowledge service is temporarily unavailable" in placeholder.content
    )
    assert placeholder.citations == []


def test_regenerate_ai_response_task_rolls_back_on_outer_error(monkeypatch):
    class FakeDB:
        def query(self, model):
            raise RuntimeError("boom")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    db = FakeDB()
    closed = []
    monkeypatch.setattr(specialist_review, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
        lambda chat_id: closed.append(chat_id),
    )
    specialist_review._regenerate_ai_response_task(1, 2, "Q", "A", "F", None, None)
    assert getattr(db, "rolled_back", False) is True
    assert getattr(db, "closed", False) is True
    assert closed == [2]


def test_send_message_rejects_invalid_status(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.APPROVED)
    with pytest.raises(HTTPException) as exc:
        specialist_service.send_message(db_session, specialist, chat.id, "hello")
    assert exc.value.status_code == 400

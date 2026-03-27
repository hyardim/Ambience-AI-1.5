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


def _mock_httpx_client(post_fn):
    """Create a mock httpx.Client class whose .post delegates to *post_fn*."""

    class _FakeClient:
        def __init__(self, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            pass

        def post(self, *args, **kwargs):
            return post_fn(*args, **kwargs)

    return _FakeClient


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


def test_build_manual_citations_detects_url_sources():
    result = specialist_service._build_manual_citations(
        ["https://nice.org.uk/guidance/ng228", "NICE NG228"]
    )
    assert result is not None
    assert len(result) == 2
    # URL source should have source_url set
    assert result[0]["title"] == "https://nice.org.uk/guidance/ng228"
    assert result[0]["source_url"] == "https://nice.org.uk/guidance/ng228"
    assert result[0]["metadata"]["source_url"] == "https://nice.org.uk/guidance/ng228"
    # Plain string source should NOT have source_url
    assert result[1]["title"] == "NICE NG228"
    assert "source_url" not in result[1]


def test_build_manual_citations_accepts_source_entry_objects():
    from src.schemas.chat import SourceEntry

    result = specialist_service._build_manual_citations(
        [
            SourceEntry(name="guideline.pdf", url="/chats/1/files/5"),
            SourceEntry(name="Plain source"),
            "Legacy string source",
        ]
    )
    assert result is not None
    assert len(result) == 3
    # SourceEntry with URL
    assert result[0]["title"] == "guideline.pdf"
    assert result[0]["source_url"] == "/chats/1/files/5"
    # SourceEntry without URL
    assert result[1]["title"] == "Plain source"
    assert "source_url" not in result[1]
    # Legacy string
    assert result[2]["title"] == "Legacy string source"
    assert "source_url" not in result[2]


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


def test_get_chat_detail_reads_fresh_state(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    _ai_message(db_session, chat)

    result = specialist_service.get_chat_detail(db_session, specialist, chat.id)

    assert result.title == "Chat"
    assert len(result.messages) == 1


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


def test_review_rejects_missing_chat_before_action_processing(db_session):
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
    assert exc.value.status_code == 404


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


def test_assign_rejects_when_chat_already_assigned(db_session):
    owner = _user(db_session, email="gp@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    other_specialist = _user(
        db_session,
        email="other@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, other_specialist, status=ChatStatus.SUBMITTED)

    with pytest.raises(HTTPException) as exc:
        specialist_service.assign(
            db_session,
            specialist,
            chat.id,
            SimpleNamespace(specialist_id=specialist.id),
        )

    assert exc.value.status_code == 409


def test_unassign_rejects_when_not_assigned_or_completed(db_session):
    owner = _user(db_session, email="gp2@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec2@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    other_specialist = _user(
        db_session,
        email="other2@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    assigned_chat = _chat(
        db_session, owner, other_specialist, status=ChatStatus.ASSIGNED
    )

    with pytest.raises(HTTPException) as exc:
        specialist_service.unassign(db_session, specialist, assigned_chat.id)
    assert exc.value.status_code == 403

    completed_chat = _chat(db_session, owner, specialist, status=ChatStatus.APPROVED)
    with pytest.raises(HTTPException) as exc:
        specialist_service.unassign(db_session, specialist, completed_chat.id)
    assert exc.value.status_code == 400


def test_unassign_rejects_when_chat_missing(db_session):
    specialist = _user(
        db_session,
        email="missing-spec@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )

    with pytest.raises(HTTPException) as exc:
        specialist_service.unassign(db_session, specialist, 99999)

    assert exc.value.status_code == 404


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


def test_review_rejects_unknown_action_when_called_directly(db_session):
    specialist = _user(
        db_session,
        email="spec-unknown-action@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )

    with pytest.raises(HTTPException) as exc:
        specialist_review.review(
            db_session,
            specialist,
            1,
            SimpleNamespace(action="unknown"),
        )

    assert exc.value.status_code == 400


def test_review_send_comment_creates_trimmed_specialist_message(
    monkeypatch, db_session
):
    owner = _user(db_session, email="gp-comment@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec-comment@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)

    monkeypatch.setattr(
        specialist_review, "invalidate_notification_caches", lambda *_args: None
    )

    response = specialist_review.review(
        db_session,
        specialist,
        chat.id,
        ReviewRequest(action="send_comment", feedback="  Please include labs  "),
    )

    comment = (
        db_session.query(Message)
        .filter(Message.chat_id == chat.id, Message.sender == "specialist")
        .order_by(Message.id.desc())
        .first()
    )
    assert response.id == chat.id
    assert comment is not None
    assert comment.content == "Please include labs"


def test_review_send_comment_requires_feedback(db_session):
    owner = _user(db_session, email="gp-comment-required@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec-comment-required@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)

    with pytest.raises(HTTPException) as exc:
        specialist_review.review(
            db_session,
            specialist,
            chat.id,
            ReviewRequest(action="send_comment", feedback="  "),
        )

    assert exc.value.status_code == 400


def test_review_unassign_resets_chat_assignment(monkeypatch, db_session):
    owner = _user(db_session, email="gp-unassign@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec-unassign@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)

    monkeypatch.setattr(
        specialist_review, "invalidate_notification_caches", lambda *_args: None
    )

    response = specialist_review.review(
        db_session,
        specialist,
        chat.id,
        ReviewRequest(action="unassign"),
    )

    db_session.refresh(chat)
    assert response.status == ChatStatus.SUBMITTED.value
    assert chat.specialist_id is None


def test_review_manual_response_requires_replacement_content(db_session):
    owner = _user(db_session, email="gp-manual-response@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec-manual-response@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)

    with pytest.raises(HTTPException) as exc:
        specialist_review.review(
            db_session,
            specialist,
            chat.id,
            ReviewRequest(action="manual_response", replacement_content=" "),
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


def test_review_rejects_request_changes_without_feedback(db_session):
    owner = _user(db_session, email="gp-feedback@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec-feedback@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)

    with pytest.raises(HTTPException) as exc:
        specialist_service.review(
            db_session,
            specialist,
            chat.id,
            ReviewRequest(action="request_changes", feedback="   "),
        )

    assert exc.value.status_code == 400
    assert "feedback" in str(exc.value.detail).lower()


def test_review_message_rejects_request_changes_without_feedback(db_session):
    owner = _user(
        db_session,
        email="gp-feedback-msg@example.com",
        role=UserRole.GP,
    )
    specialist = _user(
        db_session,
        email="spec-feedback-msg@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.ASSIGNED)
    ai_message = _ai_message(db_session, chat)

    with pytest.raises(HTTPException) as exc:
        specialist_service.review_message(
            db_session,
            specialist,
            chat.id,
            ai_message.id,
            ReviewRequest(action="request_changes", feedback="  "),
        )

    assert exc.value.status_code == 400
    assert "feedback" in str(exc.value.detail).lower()


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
    assert called["args"][8].startswith("[doc.txt]\n")
    assert called["args"][9] is False


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
        specialist_review.httpx,
        "Client",
        _mock_httpx_client(lambda *args, **kwargs: response),
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
        id=100,
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
        specialist_review.httpx,
        "Client",
        _mock_httpx_client(lambda *args, **kwargs: response),
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
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
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


def test_do_revise_forwards_internal_headers(monkeypatch):
    placeholder = SimpleNamespace(
        id=101,
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
    response.json.return_value = {"answer": "revised", "citations_used": []}

    def fake_post(url, **kwargs):
        assert kwargs.get("headers") == {"X-Internal-API-Key": "k"}
        return response

    monkeypatch.setattr(
        specialist_review, "build_rag_headers", lambda: {"X-Internal-API-Key": "k"}
    )
    monkeypatch.setattr(
        specialist_review.httpx, "Client", _mock_httpx_client(fake_post)
    )
    monkeypatch.setattr(
        specialist_review.audit_repository,
        "log",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
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

    monkeypatch.setattr(
        specialist_review.httpx, "Client", _mock_httpx_client(fail_post)
    )
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


def test_do_revise_rejects_non_dict_payload(monkeypatch):
    placeholder = SimpleNamespace(
        id=102,
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
    response.json.return_value = ["bad"]

    monkeypatch.setattr(
        specialist_review.httpx,
        "Client",
        _mock_httpx_client(lambda *args, **kwargs: response),
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
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

    assert "temporarily unavailable for revision" in placeholder.content
    assert placeholder.is_generating is False


def test_do_revise_rejects_non_string_answer(monkeypatch):
    placeholder = SimpleNamespace(
        id=103,
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
    response.json.return_value = {"answer": 123}

    monkeypatch.setattr(
        specialist_review.httpx,
        "Client",
        _mock_httpx_client(lambda *args, **kwargs: response),
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "publish_threadsafe",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        specialist_review.chat_event_bus,
        "close_chat_threadsafe",
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

    assert "temporarily unavailable for revision" in placeholder.content
    assert placeholder.is_generating is False


def test_threaded_revision_task_removed_from_specialist_review() -> None:
    assert not hasattr(specialist_review, "_regenerate_ai_response_task")


def test_threaded_revision_task_removed_from_specialist_service() -> None:
    assert not hasattr(specialist_service, "_regenerate_ai_response_task")


def test_review_message_edit_response_updates_content_and_status(db_session):
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
            action="edit_response",
            edited_content="  Edited specialist content  ",
            feedback="Clarified dosage",
        ),
    )

    db_session.refresh(ai_message)
    assert ai_message.content == "Edited specialist content"
    assert ai_message.review_status == "edited"
    assert ai_message.review_feedback == "Clarified dosage"
    assert ai_message.reviewed_at is not None
    assert response.status == "reviewing"


def test_review_message_edit_response_rejects_missing_content(db_session):
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
            ReviewRequest(action="edit_response"),
        )
    assert exc.value.status_code == 400


def test_review_message_edit_response_rejects_blank_content(db_session):
    owner = _user(db_session, email="gp3@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec3@example.com",
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
            ReviewRequest(action="edit_response", edited_content="   "),
        )
    assert exc.value.status_code == 400


def test_review_message_edit_response_with_replacement_sources(db_session):
    owner = _user(db_session, email="gp4@example.com", role=UserRole.GP)
    specialist = _user(
        db_session,
        email="spec4@example.com",
        role=UserRole.SPECIALIST,
        specialty="neurology",
    )
    chat = _chat(db_session, owner, specialist, status=ChatStatus.REVIEWING)
    ai_message = _ai_message(db_session, chat)

    specialist_service.review_message(
        db_session,
        specialist,
        chat.id,
        ai_message.id,
        ReviewRequest(
            action="edit_response",
            edited_content="Updated content with sources",
            replacement_sources=["NICE CG137", " "],
        ),
    )

    db_session.refresh(ai_message)
    assert ai_message.citations is not None
    assert ai_message.citations[0]["title"] == "NICE CG137"


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

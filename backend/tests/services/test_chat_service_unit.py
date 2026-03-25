from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.db.models import Chat, ChatStatus, FileAttachment, Message, User, UserRole
from src.schemas.chat import MessageCreate
from src.services import chat_service
from tests.conftest import TestingAsyncSessionLocal


def _user(db_session, *, email: str = "gp@example.com") -> User:
    user = User(
        email=email,
        hashed_password="hash",
        full_name="GP",
        role=UserRole.GP,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _chat(
    db_session,
    owner: User,
    *,
    status: ChatStatus = ChatStatus.OPEN,
    specialty: str = "neurology",
) -> Chat:
    chat = Chat(
        title="Chat",
        status=status,
        specialty=specialty,
        user_id=owner.id,
    )
    db_session.add(chat)
    db_session.commit()
    db_session.refresh(chat)
    return chat


def test_list_chats_rejects_invalid_status(db_session):
    user = _user(db_session)
    with pytest.raises(HTTPException) as exc:
        chat_service.list_chats(db_session, user, status="ghost")
    assert exc.value.status_code == 400


def test_list_chats_rejects_invalid_date_from(db_session):
    user = _user(db_session)
    with pytest.raises(HTTPException) as exc:
        chat_service.list_chats(db_session, user, date_from="not-a-date")
    assert exc.value.status_code == 400


def test_list_chats_rejects_invalid_date_to(db_session):
    user = _user(db_session)
    with pytest.raises(HTTPException) as exc:
        chat_service.list_chats(db_session, user, date_to="not-a-date")
    assert exc.value.status_code == 400


def test_list_chats_uses_cache_for_simple_queries(monkeypatch, db_session):
    user = _user(db_session)
    cached_item = {
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
        "user_id": user.id,
    }
    monkeypatch.setattr(
        chat_service.cache, "get_sync", lambda *args, **kwargs: [cached_item]
    )
    results = chat_service.list_chats(db_session, user)
    assert results[0].title == "Cached"


def test_update_chat_updates_severity(db_session):
    user = _user(db_session)
    chat = _chat(db_session, user)
    updated = chat_service.update_chat(
        db_session,
        user,
        chat.id,
        SimpleNamespace(title=None, specialty=None, severity="high", status=None),
    )
    assert updated.severity == "high"


def test_update_chat_rejects_invalid_status(db_session):
    user = _user(db_session)
    chat = _chat(db_session, user)
    with pytest.raises(HTTPException) as exc:
        chat_service.update_chat(
            db_session,
            user,
            chat.id,
            SimpleNamespace(title=None, specialty=None, severity=None, status="ghost"),
        )
    assert exc.value.status_code == 400


def test_get_chat_builds_file_responses(db_session):
    user = _user(db_session)
    chat = _chat(db_session, user)
    db_session.add(
        FileAttachment(
            filename="note.txt",
            file_path="/tmp/note.txt",
            file_type="text/plain",
            file_size=12,
            chat_id=chat.id,
            uploader_id=user.id,
        )
    )
    db_session.commit()
    response = chat_service.get_chat(db_session, user, chat.id)
    assert response.files[0].filename == "note.txt"


def test_get_chat_ignores_stale_cached_detail(monkeypatch, db_session):
    user = _user(db_session)
    chat = _chat(db_session, user)
    db_session.add(Message(chat_id=chat.id, content="Fresh AI", sender="ai"))
    db_session.commit()

    monkeypatch.setattr(
        chat_service.cache,
        "get_sync",
        lambda *args, **kwargs: {
            "id": chat.id,
            "title": "Stale",
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
            "user_id": user.id,
            "messages": [],
            "files": [],
        },
    )

    response = chat_service.get_chat(db_session, user, chat.id)

    assert response.title == "Chat"
    assert len(response.messages) == 1
    assert response.messages[0].content == "Fresh AI"


def test_invalidate_specialist_caches_without_specialist_id(monkeypatch):
    deleted = []
    patterns = []
    monkeypatch.setattr(
        chat_service.cache, "delete_sync", lambda *args, **kwargs: deleted.append(args)
    )
    monkeypatch.setattr(
        chat_service.cache,
        "delete_pattern_sync",
        lambda *args, **kwargs: patterns.append(args),
    )
    chat_service._invalidate_specialist_caches(specialty=None, specialist_id=None)
    assert deleted == []
    assert patterns


def test_invalidate_specialist_caches_with_specialist_id(monkeypatch):
    deleted = []
    patterns = []
    monkeypatch.setattr(
        chat_service.cache, "delete_sync", lambda *args, **kwargs: deleted.append(args)
    )
    monkeypatch.setattr(
        chat_service.cache,
        "delete_pattern_sync",
        lambda *args, **kwargs: patterns.append(args),
    )
    chat_service._invalidate_specialist_caches(specialty="neurology", specialist_id=9)
    assert deleted
    assert patterns


def test_extract_text_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert chat_service._extract_text("/tmp/missing.txt", "text/plain") == ""


def test_sanitise_filename_falls_back_when_name_is_empty():
    assert chat_service._sanitise_filename("") == "upload"


def test_build_conversation_history_ignores_empty_messages():
    messages = [
        Message(content=" Hello ", sender="user"),
        Message(content="", sender="ai"),
        Message(content=" Done ", sender="specialist"),
    ]
    history = chat_service._build_conversation_history_from_messages(messages)
    assert history == "GP: Hello\nSpecialist: Done"


def test_build_conversation_history_skips_error_messages_and_keeps_recent_tail():
    messages = [
        Message(content="Older note", sender="user"),
        Message(content="Fallback error", sender="ai", is_error=True),
        Message(content="Recent guidance", sender="ai"),
    ]
    history = chat_service._build_conversation_history_from_messages(
        messages,
        token_budget=5,
    )
    assert history == "GP: Older note"


def test_select_rag_citations_prefers_citations_used():
    assert chat_service._select_rag_citations(
        {"citations_used": [1], "citations": [2]}
    ) == [1]
    assert chat_service._select_rag_citations({"citations": [2]}) == [2]
    assert (
        chat_service._select_rag_citations(
            {"citations_used": [], "citations_retrieved": [3]}
        )
        == [3]
    )
    assert chat_service._select_rag_citations({"citations_used": []}) == []
    assert chat_service._select_rag_citations({}) is None


def test_validate_rag_response_rejects_non_dict_payload():
    with pytest.raises(ValueError, match="Expected dict"):
        chat_service._validate_rag_response(["not", "a", "dict"])


def test_validate_rag_response_rejects_non_string_answer():
    with pytest.raises(ValueError, match="Expected 'answer' to be a string"):
        chat_service._validate_rag_response({"answer": 123})


def test_message_create_rejects_whitespace_only_content():
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")


def test_archive_chat_logs_warning_when_file_delete_fails(monkeypatch, db_session):
    user = _user(db_session)
    chat = _chat(db_session, user)
    attachment = FileAttachment(
        filename="note.txt",
        file_path="/tmp/failing.txt",
        file_type="text/plain",
        file_size=12,
        chat_id=chat.id,
        uploader_id=user.id,
    )
    db_session.add(attachment)
    db_session.commit()

    monkeypatch.setattr(chat_service.os.path, "exists", lambda path: True)

    def boom(_path):
        raise OSError("cannot delete")

    monkeypatch.setattr(chat_service.os, "remove", boom)
    monkeypatch.setattr(chat_service.audit_repository, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_service.cache, "delete_pattern_sync", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_service, "invalidate_admin_chat_caches_sync", lambda *args, **kwargs: None)
    warnings = []
    monkeypatch.setattr(chat_service.logger, "warning", lambda *args, **kwargs: warnings.append(args))

    chat_service.archive_chat(db_session, user, chat.id)

    db_session.refresh(chat)
    assert chat.is_archived is True
    assert warnings


@pytest.mark.asyncio
async def test_async_generate_ai_response_returns_when_chat_missing(monkeypatch):
    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    close_chat = AsyncMock()
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", close_chat)
    monkeypatch.setattr(
        chat_service.chat_repository, "async_get_for_update", AsyncMock(return_value=None)
    )

    await chat_service._async_generate_ai_response(999, 1, "hello")

    close_chat.assert_awaited_once_with(999)


@pytest.mark.asyncio
async def test_async_generate_ai_response_skips_when_existing_generation_found(
    monkeypatch, db_session
):
    user = _user(db_session)
    chat = _chat(db_session, user, status=ChatStatus.SUBMITTED)
    db_session.add(Message(chat_id=chat.id, content="busy", sender="ai", is_generating=True))
    db_session.commit()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    publish = AsyncMock()
    close_chat = AsyncMock()
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", publish)
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", close_chat)

    await chat_service._async_generate_ai_response(chat.id, user.id, "Question")

    publish.assert_not_awaited()
    close_chat.assert_awaited_once_with(chat.id)


@pytest.mark.asyncio
async def test_async_generate_ai_response_uses_sync_httpx_path_in_sqlite(
    monkeypatch, db_session
):
    user = _user(db_session)
    chat = _chat(db_session, user, status=ChatStatus.SUBMITTED)
    db_session.add(Message(chat_id=chat.id, content="Question", sender="user"))
    db_session.commit()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", AsyncMock())
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "answer": "AI answer",
        "citations_used": [{"title": "Doc"}],
    }
    monkeypatch.setattr(chat_service.httpx, "post", lambda *args, **kwargs: response)

    await chat_service._async_generate_ai_response(chat.id, user.id, "Question")

    refreshed = (
        db_session.query(Message)
        .filter(Message.chat_id == chat.id, Message.sender == "ai")
        .one()
    )
    assert refreshed.content == "AI answer"
    assert refreshed.is_generating is False


@pytest.mark.asyncio
async def test_async_generate_ai_response_falls_back_to_async_client_post(
    monkeypatch, db_session
):
    user = _user(db_session)
    chat = _chat(db_session, user, status=ChatStatus.SUBMITTED)
    db_session.add(Message(chat_id=chat.id, content="Question", sender="user"))
    db_session.commit()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", AsyncMock())
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())
    monkeypatch.setattr(
        chat_service.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("sync fail")),
    )

    class FakeAsyncResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": "Async fallback", "citations": []}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json=None, **kwargs):
            return FakeAsyncResponse()

    monkeypatch.setattr(chat_service.httpx, "AsyncClient", FakeAsyncClient)

    await chat_service._async_generate_ai_response(chat.id, user.id, "Question")

    refreshed = (
        db_session.query(Message)
        .filter(Message.chat_id == chat.id, Message.sender == "ai")
        .one()
    )
    assert refreshed.content == "Async fallback"


@pytest.mark.asyncio
async def test_async_generate_ai_response_fallback_forwards_internal_headers(
    monkeypatch, db_session
):
    user = _user(db_session)
    chat = _chat(db_session, user, status=ChatStatus.SUBMITTED)
    db_session.add(Message(chat_id=chat.id, content="Question", sender="user"))
    db_session.commit()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", AsyncMock())
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())
    monkeypatch.setattr(
        chat_service, "build_rag_headers", lambda: {"X-Internal-API-Key": "k"}
    )
    monkeypatch.setattr(
        chat_service.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("sync fail")),
    )

    class FakeAsyncResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": "Async fallback", "citations": []}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json, headers=None):
            assert headers == {"X-Internal-API-Key": "k"}
            return FakeAsyncResponse()

    monkeypatch.setattr(chat_service.httpx, "AsyncClient", FakeAsyncClient)

    await chat_service._async_generate_ai_response(chat.id, user.id, "Question")


@pytest.mark.asyncio
async def test_async_generate_ai_response_streaming_forwards_internal_headers(
    monkeypatch,
):
    monkeypatch.setattr(chat_service.settings, "INLINE_AI_TASKS", False)
    publish = AsyncMock()
    close_chat = AsyncMock()
    async_update = AsyncMock()
    placeholder = SimpleNamespace(id=77)
    fake_chat = SimpleNamespace(
        id=5,
        user_id=9,
        specialty="neurology",
        severity=None,
        patient_context=None,
        files=[],
        specialist_id=None,
    )

    class FakeScalars:
        def first(self):
            return None

        def __iter__(self):
            return iter([])

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return FakeResult()

        async def rollback(self):
            return None

    class FakeStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield '{"type":"done","answer":"Hello world","citations_used":[]}'

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json, headers=None):
            assert headers == {"X-Internal-API-Key": "k"}
            return FakeStreamResponse()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        chat_service.chat_repository,
        "async_get_for_update",
        AsyncMock(return_value=fake_chat),
    )
    monkeypatch.setattr(
        chat_service.message_repository,
        "async_create",
        AsyncMock(return_value=placeholder),
    )
    monkeypatch.setattr(chat_service.message_repository, "async_update", async_update)
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", publish)
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", close_chat)
    monkeypatch.setattr(
        chat_service, "build_rag_headers", lambda: {"X-Internal-API-Key": "k"}
    )
    monkeypatch.setattr(chat_service.httpx, "AsyncClient", FakeAsyncClient)

    await chat_service._async_generate_ai_response(5, 9, "Question")


@pytest.mark.asyncio
async def test_async_generate_ai_response_inline_forwards_internal_headers(
    monkeypatch, db_session
):
    monkeypatch.setattr(chat_service.settings, "INLINE_AI_TASKS", True)
    user = _user(db_session)
    chat = _chat(db_session, user, status=ChatStatus.SUBMITTED)
    db_session.add(Message(chat_id=chat.id, content="Question", sender="user"))
    db_session.commit()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", AsyncMock())
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())
    monkeypatch.setattr(
        chat_service, "build_rag_headers", lambda: {"X-Internal-API-Key": "k"}
    )

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"answer": "AI answer", "citations_used": []}

    def fake_post(url, json, timeout, headers=None):
        assert headers == {"X-Internal-API-Key": "k"}
        return response

    monkeypatch.setattr(chat_service.httpx, "post", fake_post)

    await chat_service._async_generate_ai_response(chat.id, user.id, "Question")


@pytest.mark.asyncio
async def test_async_generate_ai_response_publishes_error_on_failure(
    monkeypatch, db_session
):
    user = _user(db_session)
    chat = _chat(db_session, user, status=ChatStatus.SUBMITTED)

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", TestingAsyncSessionLocal)
    monkeypatch.setattr(
        chat_service.message_repository,
        "async_create",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    publish = AsyncMock()
    close_chat = AsyncMock()
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", publish)
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", close_chat)

    await chat_service._async_generate_ai_response(chat.id, user.id, "Question")

    assert publish.await_count == 1
    close_chat.assert_awaited_once_with(chat.id)


@pytest.mark.asyncio
async def test_async_generate_ai_response_streaming_path_handles_chunks_and_done(
    monkeypatch,
):
    monkeypatch.setattr(chat_service.settings, "INLINE_AI_TASKS", False)
    publish = AsyncMock()
    close_chat = AsyncMock()
    async_update = AsyncMock()
    async_log = AsyncMock()
    delete_pattern = AsyncMock()
    delete = AsyncMock()
    placeholder = SimpleNamespace(id=77)
    fake_chat = SimpleNamespace(
        id=5,
        user_id=9,
        specialty="neurology",
        severity=None,
        patient_context=None,
        files=[
            SimpleNamespace(
                filename="doc.txt", file_path="/tmp/doc.txt", file_type="text/plain"
            )
        ],
        specialist_id=None,
    )

    class FakeScalars:
        def first(self):
            return None

        def __iter__(self):
            return iter([])

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return FakeResult()

        async def rollback(self):
            return None

    class FakeSessionFactory:
        def __call__(self):
            return FakeDB()

    class FakeStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield ""
            yield '{"type":"chunk","delta":"Hello"}'
            yield "not-json"
            yield '{"type":"done","answer":"Hello world","citations_used":[{"title":"Doc"}]}'

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json=None, **kwargs):
            return FakeStreamResponse()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", FakeSessionFactory())
    monkeypatch.setattr(
        chat_service.chat_repository,
        "async_get_for_update",
        AsyncMock(return_value=fake_chat),
    )
    monkeypatch.setattr(
        chat_service.message_repository,
        "async_create",
        AsyncMock(return_value=placeholder),
    )
    monkeypatch.setattr(chat_service.message_repository, "async_update", async_update)
    monkeypatch.setattr(chat_service.audit_repository, "async_log", async_log)
    monkeypatch.setattr(chat_service.cache, "delete_pattern", delete_pattern)
    monkeypatch.setattr(chat_service.cache, "delete", delete)
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", publish)
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", close_chat)
    monkeypatch.setattr(chat_service, "_extract_text", lambda *args: "x" * 9000)
    monkeypatch.setattr(chat_service.httpx, "AsyncClient", FakeAsyncClient)

    await chat_service._async_generate_ai_response(5, 9, "Question")

    update_kwargs = async_update.await_args.kwargs
    assert update_kwargs["content"] == "Hello world"
    assert update_kwargs["citations"] == [{"title": "Doc"}]
    assert publish.await_count == 4
    published_events = [call.args[1].event for call in publish.await_args_list]
    assert published_events == ["stream_start", "content", "content", "complete"]
    assert publish.await_args_list[1].args[1].data.get("is_draft") is True
    close_chat.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_async_generate_ai_response_streaming_error_chunk_falls_back(
    monkeypatch,
):
    monkeypatch.setattr(chat_service.settings, "INLINE_AI_TASKS", False)
    publish = AsyncMock()
    close_chat = AsyncMock()
    async_update = AsyncMock()
    placeholder = SimpleNamespace(id=77)
    fake_chat = SimpleNamespace(
        id=5,
        user_id=9,
        specialty=None,
        severity=None,
        patient_context=None,
        files=[],
        specialist_id=None,
    )

    class FakeScalars:
        def first(self):
            return None

        def __iter__(self):
            return iter([])

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeDB:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def execute(self, stmt):
            return FakeResult()

        async def rollback(self):
            return None

    class FakeStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield '{"type":"error","error":"bad stream"}'

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json=None, **kwargs):
            return FakeStreamResponse()

    monkeypatch.setattr(chat_service, "AsyncSessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        chat_service.chat_repository,
        "async_get_for_update",
        AsyncMock(return_value=fake_chat),
    )
    monkeypatch.setattr(
        chat_service.message_repository,
        "async_create",
        AsyncMock(return_value=placeholder),
    )
    monkeypatch.setattr(chat_service.message_repository, "async_update", async_update)
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service.chat_event_bus, "publish", publish)
    monkeypatch.setattr(chat_service.chat_event_bus, "close_chat", close_chat)
    monkeypatch.setattr(chat_service.httpx, "AsyncClient", FakeAsyncClient)

    await chat_service._async_generate_ai_response(5, 9, "Question")

    update_kwargs = async_update.await_args.kwargs
    assert (
        "clinical knowledge service is temporarily unavailable"
        in update_kwargs["content"]
    )
    assert update_kwargs["citations"] is None


@pytest.mark.asyncio
async def test_async_send_message_auto_submits_open_chat(monkeypatch):
    chat = SimpleNamespace(
        id=1,
        status=ChatStatus.OPEN,
        user_id=1,
        specialty=None,
        specialist_id=None,
    )
    fake_db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )
    monkeypatch.setattr(
        chat_service.chat_repository, "async_get", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr(chat_service.message_repository, "async_create", AsyncMock())
    updated = AsyncMock()
    monkeypatch.setattr(chat_service.chat_repository, "async_update", updated)
    logged = AsyncMock()
    monkeypatch.setattr(chat_service.audit_repository, "async_log", logged)
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    monkeypatch.setattr(chat_service, "_async_generate_ai_response", AsyncMock())

    await chat_service.async_send_message(fake_db, SimpleNamespace(id=1), 1, "hello")

    updated.assert_awaited_once()
    logged.assert_awaited()


@pytest.mark.asyncio
async def test_async_send_message_rejects_missing_chat(monkeypatch):
    monkeypatch.setattr(
        chat_service.chat_repository, "async_get", AsyncMock(return_value=None)
    )
    fake_db = SimpleNamespace()
    with pytest.raises(HTTPException) as exc:
        await chat_service.async_send_message(
            fake_db, SimpleNamespace(id=1), 999, "hello"
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_async_send_message_rejects_invalid_status(monkeypatch):
    chat = SimpleNamespace(
        id=1,
        status=ChatStatus.APPROVED,
        user_id=1,
        specialty=None,
        specialist_id=None,
    )
    monkeypatch.setattr(
        chat_service.chat_repository, "async_get", AsyncMock(return_value=chat)
    )
    fake_db = SimpleNamespace()
    with pytest.raises(HTTPException) as exc:
        await chat_service.async_send_message(
            fake_db, SimpleNamespace(id=1), 1, "hello"
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_async_send_message_uses_background_task_for_non_sqlite(monkeypatch):
    monkeypatch.setattr(chat_service.settings, "INLINE_AI_TASKS", False)
    chat = SimpleNamespace(
        id=1,
        status=ChatStatus.SUBMITTED,
        user_id=1,
        specialty=None,
        specialist_id=None,
    )
    fake_db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    monkeypatch.setattr(
        chat_service.chat_repository, "async_get", AsyncMock(return_value=chat)
    )
    monkeypatch.setattr(chat_service.message_repository, "async_create", AsyncMock())
    monkeypatch.setattr(chat_service.chat_repository, "async_update", AsyncMock())
    monkeypatch.setattr(chat_service.audit_repository, "async_log", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete_pattern", AsyncMock())
    monkeypatch.setattr(chat_service.cache, "delete", AsyncMock())
    created = []

    def fake_create_task(coro, **kwargs):
        created.append(coro)
        fake_task = SimpleNamespace(add_done_callback=lambda cb: None)
        return fake_task

    monkeypatch.setattr(chat_service.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(chat_service, "_async_generate_ai_response", AsyncMock())

    result = await chat_service.async_send_message(
        fake_db, SimpleNamespace(id=1), 1, "hello"
    )

    assert result["ai_generating"] is True
    assert created
    created[0].close()


def test_on_generation_task_done_logs_cancelled_task(monkeypatch):
    calls = []

    class FakeTask:
        def cancelled(self):
            return True

        def get_name(self):
            return "ai-gen-chat-1"

    monkeypatch.setattr(
        chat_service.logger,
        "info",
        lambda message, *args: calls.append((message, args)),
    )

    chat_service._on_generation_task_done(FakeTask())

    assert calls == [("AI generation task %s was cancelled", ("ai-gen-chat-1",))]


def test_on_generation_task_done_logs_task_exception(monkeypatch):
    calls = []
    exc = RuntimeError("boom")

    class FakeTask:
        def cancelled(self):
            return False

        def exception(self):
            return exc

        def get_name(self):
            return "ai-gen-chat-2"

    monkeypatch.setattr(
        chat_service.logger,
        "error",
        lambda message, *args, **kwargs: calls.append((message, args, kwargs)),
    )

    chat_service._on_generation_task_done(FakeTask())

    assert calls == [
        (
            "AI generation task %s failed: %s",
            ("ai-gen-chat-2", exc),
            {"exc_info": exc},
        )
    ]

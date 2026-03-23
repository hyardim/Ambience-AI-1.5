from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Optional, Protocol

import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import Chat, ChatStatus, FileAttachment, Message, User
from src.db.session import AsyncSessionLocal
from src.repositories import audit_repository, chat_repository, message_repository
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
    FileAttachmentResponse,
)
from src.services import chat_uploads
from src.services._mappers import chat_to_response, msg_to_response
from src.services.cache_invalidation import (
    invalidate_admin_chat_caches_sync,
    invalidate_admin_stats_sync,
    invalidate_chat_related_async,
    invalidate_chat_related_sync,
    invalidate_specialist_lists_sync,
)
from src.services.chat_uploads import (
    sanitise_filename,
    upload_chat_file,
    validate_upload_extension,
)
from src.services.rag_client import build_rag_headers
from src.services.rag_context import (
    FileContextBuildResult,
    build_conversation_history_from_messages,
    build_file_context,
    build_file_context_result,
    build_patient_context,
    extract_text,
    select_rag_citations,
)
from src.utils.cache import cache, cache_keys
from src.utils.sse import SSEEvent, chat_event_bus

RAG_SERVICE_URL = settings.RAG_SERVICE_URL
RAG_REQUEST_TIMEOUT_SECONDS = settings.RAG_REQUEST_TIMEOUT_SECONDS
CHAT_RAG_TOP_K = settings.CHAT_RAG_TOP_K
UPLOAD_DIR = chat_uploads.UPLOAD_DIR

logger = logging.getLogger(__name__)


def _validate_rag_response(rag_json: Any) -> dict:
    """Validate that a RAG service response is a dict with an 'answer' string.

    Returns the validated dict, or raises ValueError if the shape is wrong.
    """
    if not isinstance(rag_json, dict):
        raise ValueError(f"Expected dict from RAG service, got {type(rag_json).__name__}")
    answer = rag_json.get("answer")
    if answer is not None and not isinstance(answer, str):
        raise ValueError(f"Expected 'answer' to be a string, got {type(answer).__name__}")
    return rag_json


def _invalidate_specialist_caches(
    *,
    specialty: str | None = None,
    specialist_id: int | None = None,
) -> None:
    invalidate_specialist_lists_sync(
        specialty=specialty,
        specialist_id=specialist_id,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_chat(db: Session, user: User, data: ChatCreate) -> ChatResponse:
    """Create a new chat with optional patient context.

    Args:
        db: Database session.
        user: The GP user creating the chat.
        data: Chat creation payload including title, specialty, and patient info.

    Returns:
        The newly created chat as a ChatResponse.
    """
    patient_context = {
        k: v
        for k, v in {
            "age": data.patient_age,
            "gender": data.patient_gender,
            "notes": data.patient_notes,
        }.items()
        if v is not None
    } or None

    chat = chat_repository.create(
        db,
        user_id=user.id,
        title=data.title,
        specialty=data.specialty,
        severity=data.severity,
        patient_context=patient_context,
    )
    audit_repository.log(
        db, user_id=user.id, action="CREATE_CHAT", details=f"Created chat: {data.title}"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    invalidate_admin_chat_caches_sync(chat.id)
    invalidate_admin_stats_sync()
    return chat_to_response(chat)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def list_chats(
    db: Session,
    user: User,
    *,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[ChatResponse]:
    """List chats belonging to a user with optional filters and pagination.

    Args:
        db: Database session.
        user: The owning user.
        skip: Number of records to skip for pagination.
        limit: Maximum number of records to return.
        status: Optional chat status filter.
        specialty: Optional specialty filter.
        search: Optional free-text search term.
        date_from: Optional ISO-8601 start date filter.
        date_to: Optional ISO-8601 end date filter.

    Returns:
        A list of ChatResponse objects matching the criteria.
    """
    if status:
        try:
            ChatStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    parsed_date_from = None
    parsed_date_to = None
    if date_from:
        try:
            parsed_date_from = datetime.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid date_from: {date_from}"
            )
    if date_to:
        try:
            parsed_date_to = datetime.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date_to: {date_to}")

    # Avoid cache collisions for filter combinations not encoded in cache key.
    should_cache = not (search or date_from or date_to)
    cache_key = None
    if should_cache:
        page = skip // limit if limit else 0
        cache_key = cache_keys.chat_list(
            user.id, page, limit, status=status, specialty=specialty
        )
        cached = cache.get_sync(cache_key, user_id=user.id, resource="chat_list")
        if cached is not None:
            return [ChatResponse(**item) for item in cached]

    chats = chat_repository.list_for_user(
        db,
        user.id,
        skip=skip,
        limit=limit,
        status=status,
        specialty=specialty,
        search=search,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
    )
    response = [chat_to_response(c) for c in chats]
    if should_cache and cache_key is not None:
        cache.set_sync(
            cache_key,
            [item.model_dump() for item in response],
            ttl=settings.CACHE_CHAT_LIST_TTL,
            user_id=user.id,
            resource="chat_list",
        )
    return response


# ---------------------------------------------------------------------------
# Get (with messages)
# ---------------------------------------------------------------------------


def get_chat(db: Session, user: User, chat_id: int) -> ChatWithMessages:
    """Retrieve a single chat with all its messages and file attachments.

    Args:
        db: Database session.
        user: The owning user.
        chat_id: Primary key of the chat.

    Returns:
        The chat details including messages and files.

    Raises:
        HTTPException: If the chat is not found.
    """
    cache_key = cache_keys.chat_detail(user.id, chat_id)
    cached = cache.get_sync(cache_key, user_id=user.id, resource="chat_detail")
    if cached is not None:
        return ChatWithMessages(**cached)

    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    audit_repository.log(
        db, user_id=user.id, action="VIEW_CHAT", details=f"Viewed chat {chat_id}"
    )
    messages = message_repository.list_for_chat(db, chat.id)
    response = ChatWithMessages(**chat_to_response(chat).model_dump())
    response.messages = [msg_to_response(m) for m in messages]
    response.files = [
        FileAttachmentResponse(
            id=f.id,
            filename=f.filename,
            file_type=f.file_type,
            file_size=f.file_size,
            created_at=f.created_at.isoformat() if f.created_at else "",
        )
        for f in (chat.files or [])
    ]
    cache.set_sync(
        cache_key,
        response.model_dump(),
        ttl=settings.CACHE_CHAT_DETAIL_TTL,
        user_id=user.id,
        resource="chat_detail",
    )
    return response


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update_chat(
    db: Session, user: User, chat_id: int, payload: ChatUpdate
) -> ChatResponse:
    """Update editable metadata on a chat (title, specialty, severity, status).

    Args:
        db: Database session.
        user: The owning user.
        chat_id: Primary key of the chat.
        payload: Fields to update.

    Returns:
        The updated ChatResponse.

    Raises:
        HTTPException: If the chat is not found or is no longer editable.
    """
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Block metadata edits after specialist assignment
    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit chat details after specialist assignment (current: {chat.status.value})",
        )

    fields: dict = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty
    if payload.severity is not None:
        fields["severity"] = payload.severity
    if payload.status is not None:
        try:
            fields["status"] = ChatStatus(payload.status)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {payload.status}"
            )

    chat = chat_repository.update(db, chat, **fields)
    audit_repository.log(
        db, user_id=user.id, action="UPDATE_CHAT", details=f"Updated chat {chat_id}"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    invalidate_admin_chat_caches_sync(chat_id)
    return chat_to_response(chat)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def archive_chat(db: Session, user: User, chat_id: int) -> None:
    """Archive a chat and remove associated file attachments from disk."""
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Clean up uploaded files from the filesystem before archiving
    attachments = db.query(FileAttachment).filter(FileAttachment.chat_id == chat_id).all()
    for att in attachments:
        if att.file_path and os.path.exists(att.file_path):
            try:
                os.remove(att.file_path)
            except OSError:
                logger.warning("Failed to remove file %s for chat %s", att.file_path, chat_id)

    chat_repository.archive(db, chat)
    audit_repository.log(
        db, user_id=user.id, action="ARCHIVE_CHAT", details=f"Archived chat {chat_id}"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    invalidate_admin_chat_caches_sync(chat_id)


# ---------------------------------------------------------------------------
# File uploads
# ---------------------------------------------------------------------------


_extract_text = extract_text
_build_conversation_history_from_messages = build_conversation_history_from_messages
_select_rag_citations = select_rag_citations
_sanitise_filename = sanitise_filename
_validate_upload_extension = validate_upload_extension


def _build_patient_context(chat: Chat, messages: list[Message]) -> dict | None:
    return build_patient_context(chat, messages)


def _build_file_context(chat: Chat) -> str | None:
    return build_file_context(chat, extract_text_fn=_extract_text)


def _build_file_context_result(chat: Chat) -> FileContextBuildResult:
    return build_file_context_result(chat, extract_text_fn=_extract_text)


async def upload_file(
    db: Session,
    user: User,
    chat_id: int,
    file: UploadFile,
) -> FileAttachmentResponse:
    """Upload a file attachment to an existing chat.

    Args:
        db: Database session.
        user: The uploading user.
        chat_id: Target chat primary key.
        file: The uploaded file from the request.

    Returns:
        Metadata about the persisted file attachment.
    """
    chat_uploads.UPLOAD_DIR = UPLOAD_DIR
    attachment = await upload_chat_file(db, user, chat_id, file)

    return FileAttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        file_type=attachment.file_type,
        file_size=attachment.file_size,
        created_at=attachment.created_at.isoformat() if attachment.created_at else "",
    )


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Async send message  (chat/RAG path — non-blocking)
# ---------------------------------------------------------------------------


async def _async_generate_ai_response(chat_id: int, user_id: int, content: str) -> None:
    """Generate an AI response using async HTTP + async DB.

    Includes a concurrency guard: if another generation is already in
    progress for this chat (``is_generating=True``), the call is skipped.

    Publishes SSE lifecycle events so connected clients receive real-time
    updates.  The flow:
      1. Check for an existing in-progress generation; bail out if found.
      2. Create a placeholder message with ``is_generating=True``.
      3. Publish ``stream_start``.
      4. Call the RAG service with streaming enabled.
      5. Publish cumulative ``content`` events as tokens arrive.
      6. Finalise the message (content, citations, ``is_generating=False``).
      7. Publish ``complete`` with citations.
      8. Close the chat's event bus so SSE clients disconnect cleanly.
    """
    async with AsyncSessionLocal() as db:
        try:
            chat = await chat_repository.async_get_for_update(db, chat_id)
            if not chat:
                return

            # Concurrency guard: skip if another generation is already running
            existing = (
                await db.execute(
                    select(Message).where(
                        Message.chat_id == chat_id,
                        Message.is_generating == True,  # noqa: E712
                    )
                )
            )
            if existing.scalars().first() is not None:
                logger.info(
                    "Skipping AI generation for chat %s – already generating", chat_id
                )
                return

            # 1. Placeholder message
            placeholder = await message_repository.async_create(
                db,
                chat_id=chat.id,
                content="",
                sender="ai",
                is_generating=True,
            )

            # 2. stream_start
            await chat_event_bus.publish(
                chat_id,
                SSEEvent(
                    event="stream_start",
                    data={"chat_id": chat_id, "message_id": placeholder.id},
                ),
            )

            message_rows = await db.execute(
                select(Message)
                .where(Message.chat_id == chat.id)
                .order_by(Message.created_at.asc())
            )
            messages = list(message_rows.scalars())
            patient_context = _build_patient_context(chat, messages)
            file_context_result = _build_file_context_result(chat)
            file_context = file_context_result.file_context

            rag_payload: dict = {
                "query": content,
                "top_k": CHAT_RAG_TOP_K,
                "stream": True,
                "specialty": chat.specialty,
                "severity": chat.severity,
                "patient_context": patient_context,
            }
            if file_context:
                rag_payload["file_context"] = file_context
            rag_payload["file_context_truncated"] = file_context_result.was_truncated

            rag_action = "RAG_ERROR"
            rag_details = f"query_len={len(content)} error=unknown"
            ai_content = ""
            citations = None
            try:
                if settings.INLINE_AI_TASKS:
                    try:
                        rag_headers = build_rag_headers()
                        request_kwargs_inline: dict[str, Any] = {}
                        if rag_headers:
                            request_kwargs_inline["headers"] = rag_headers
                        rag_response = httpx.post(
                            f"{RAG_SERVICE_URL}/answer",
                            json=rag_payload,
                            timeout=RAG_REQUEST_TIMEOUT_SECONDS,
                            **request_kwargs_inline,
                        )
                        rag_response.raise_for_status()
                        rag_json = _validate_rag_response(rag_response.json())
                    except Exception:
                        # Compatibility for tests that patch AsyncClient.post.
                        async with httpx.AsyncClient(
                            timeout=RAG_REQUEST_TIMEOUT_SECONDS
                        ) as client:
                            rag_headers = build_rag_headers()
                            request_kwargs_fallback: dict[str, Any] = {}
                            if rag_headers:
                                request_kwargs_fallback["headers"] = rag_headers
                            rag_response = await client.post(
                                f"{RAG_SERVICE_URL}/answer",
                                json=rag_payload,
                                **request_kwargs_fallback,
                            )
                            rag_response.raise_for_status()
                            rag_json = _validate_rag_response(rag_response.json())

                    ai_content = rag_json.get("answer", "")
                    citations = _select_rag_citations(rag_json)
                else:
                    async with httpx.AsyncClient(
                        timeout=RAG_REQUEST_TIMEOUT_SECONDS
                    ) as client:
                        rag_headers = build_rag_headers()
                        request_kwargs_stream: dict[str, Any] = {}
                        if rag_headers:
                            request_kwargs_stream["headers"] = rag_headers
                        async with client.stream(
                            "POST",
                            f"{RAG_SERVICE_URL}/answer",
                            json=rag_payload,
                            **request_kwargs_stream,
                        ) as rag_response:
                            rag_response.raise_for_status()
                            async for line in rag_response.aiter_lines():
                                if not line.strip():
                                    continue
                                try:
                                    chunk = json.loads(line)
                                except json.JSONDecodeError:
                                    continue

                                if chunk.get("type") == "chunk":
                                    ai_content += chunk.get("delta", "")
                                    await chat_event_bus.publish(
                                        chat_id,
                                        SSEEvent(
                                            event="content",
                                            data={
                                                "chat_id": chat_id,
                                                "message_id": placeholder.id,
                                                "content": ai_content,
                                            },
                                        ),
                                    )
                                elif chunk.get("type") == "done":
                                    ai_content = chunk.get("answer", ai_content)
                                    citations = _select_rag_citations(chunk)
                                elif chunk.get("type") == "error":
                                    raise RuntimeError(
                                        chunk.get("error", "RAG streaming error")
                                    )

                rag_action = "RAG_ANSWER"
                rag_details = (
                    f"query_len={len(content)} top_k={CHAT_RAG_TOP_K} "
                    f"chunks_used={len(citations) if citations else 0}"
                )
            except Exception as exc:
                logger.warning("RAG request failed for chat %s: %s", chat_id, exc)
                ai_content = (
                    "The clinical knowledge service is temporarily unavailable. "
                    "Please try again shortly or contact support if the issue persists."
                )
                citations = None
                rag_details = f"query_len={len(content)} error={type(exc).__name__}"

            await audit_repository.async_log(
                db, user_id=user_id, action=rag_action, details=rag_details
            )

            # Publish a final content event so late subscribers see the result
            # even if they missed the incremental chunks.
            await chat_event_bus.publish(
                chat_id,
                SSEEvent(
                    event="content",
                    data={
                        "chat_id": chat_id,
                        "message_id": placeholder.id,
                        "content": ai_content,
                    },
                ),
            )

            # 5. Finalise placeholder
            await message_repository.async_update(
                db,
                placeholder,
                content=ai_content,
                citations=citations,
                is_generating=False,
            )

            await audit_repository.async_log(
                db,
                user_id=user_id,
                action="AI_RESPONSE_GENERATED",
                details=f"AI response generated for chat {chat_id}",
            )

            await invalidate_chat_related_async(
                chat_id=chat_id,
                user_id=chat.user_id,
                specialty=chat.specialty,
                specialist_id=chat.specialist_id,
            )

            # 6. complete event
            await chat_event_bus.publish(
                chat_id,
                SSEEvent(
                    event="complete",
                    data={
                        "chat_id": chat_id,
                        "message_id": placeholder.id,
                        "content": ai_content,
                        "citations": citations,
                        "file_context_truncated": file_context_result.was_truncated,
                    },
                ),
            )
        except Exception:
            await db.rollback()
            logger.exception("Async AI generation failed for chat %s", chat_id)
            # Notify any waiting SSE subscribers about the failure
            await chat_event_bus.publish(
                chat_id,
                SSEEvent(
                    event="error",
                    data={
                        "chat_id": chat_id,
                        "message_id": 0,
                        "error": "Internal generation error",
                    },
                ),
            )
        finally:
            # 7. Close the bus so SSE clients disconnect
            await chat_event_bus.close_chat(chat_id)


class _GenerationTaskLike(Protocol):
    def cancelled(self) -> bool: ...

    def exception(self) -> BaseException | None: ...

    def get_name(self) -> str: ...


def _on_generation_task_done(task: _GenerationTaskLike) -> None:
    """Log unhandled exceptions from background AI generation tasks."""
    if task.cancelled():
        logger.info("AI generation task %s was cancelled", task.get_name())
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "AI generation task %s failed: %s",
            task.get_name(),
            exc,
            exc_info=exc,
        )


async def async_send_message(
    db: AsyncSession,
    user: User,
    chat_id: int,
    content: str,
) -> dict:
    """Send a user message and trigger asynchronous AI response generation.

    Args:
        db: Async database session.
        user: The GP user sending the message.
        chat_id: Target chat primary key.
        content: The message text.

    Returns:
        A dict indicating the message was sent and AI generation has started.

    Raises:
        HTTPException: If the chat is not found or not in a messageable state.
    """
    if hasattr(db, "execute"):
        chat = await chat_repository.async_get_for_update(db, chat_id, user_id=user.id)
    else:
        # Test doubles may provide only minimal DB shape.
        chat = await chat_repository.async_get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send messages in {chat.status.value} state",
        )

    await message_repository.async_create(
        db, chat_id=chat.id, content=content, sender="user"
    )

    if chat.status == ChatStatus.OPEN:
        await chat_repository.async_update(db, chat, status=ChatStatus.SUBMITTED)
        await audit_repository.async_log(
            db,
            user_id=user.id,
            action="AUTO_SUBMIT_FOR_REVIEW",
            details=f"Chat {chat_id} auto-submitted after first GP message",
        )

    # Async task for AI generation.
    # Under SQLite (tests) run inline so assertions can see the result.
    if settings.INLINE_AI_TASKS:
        await _async_generate_ai_response(chat.id, user.id, content)
    else:
        task = asyncio.create_task(
            _async_generate_ai_response(chat.id, user.id, content),
            name=f"ai-gen-chat-{chat.id}",
        )
        task.add_done_callback(_on_generation_task_done)

    await invalidate_chat_related_async(
        chat_id=chat_id,
        user_id=chat.user_id,
        specialty=chat.specialty,
        specialist_id=chat.specialist_id,
    )

    return {
        "status": "Message sent",
        "ai_response": f"AI response is being generated for: {content}",
        "ai_generating": True,
    }


# ---------------------------------------------------------------------------
# Submit for review
# ---------------------------------------------------------------------------


def submit_for_review(db: Session, user: User, chat_id: int) -> ChatResponse:
    """Transition an OPEN chat to SUBMITTED status for specialist review.

    Args:
        db: Database session.
        user: The owning user.
        chat_id: Primary key of the chat.

    Returns:
        The updated ChatResponse.

    Raises:
        HTTPException: If the chat is not found or not in OPEN status.
    """
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.OPEN:
        raise HTTPException(
            status_code=400,
            detail=f"Only OPEN chats can be submitted (current: {chat.status.value})",
        )

    chat = chat_repository.update(db, chat, status=ChatStatus.SUBMITTED)
    audit_repository.log(
        db,
        user_id=user.id,
        action="SUBMIT_FOR_REVIEW",
        details=f"Chat {chat_id} submitted for specialist review",
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user.id), user_id=user.id, resource="chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    invalidate_chat_related_sync(
        chat_id=chat_id,
        user_id=chat.user_id,
        specialty=chat.specialty,
        specialist_id=chat.specialist_id,
    )
    return chat_to_response(chat)

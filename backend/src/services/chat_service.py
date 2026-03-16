from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Optional

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
from src.services._mappers import chat_to_response, msg_to_response
from src.services.cache_invalidation import (
    invalidate_admin_chat_caches_sync,
    invalidate_admin_stats_sync,
    invalidate_chat_related_async,
    invalidate_chat_related_sync,
    invalidate_specialist_lists_sync,
)
from src.services.rag_context import (
    build_conversation_history_from_messages,
    build_file_context,
    build_patient_context,
    extract_text,
    select_rag_citations,
)
from src.utils.cache import cache, cache_keys
from src.utils.sse import SSEEvent, chat_event_bus

RAG_SERVICE_URL = settings.RAG_SERVICE_URL
UPLOAD_DIR = Path(settings.UPLOAD_DIR)
MAX_FILE_SIZE_BYTES = settings.MAX_FILE_SIZE_BYTES
MAX_FILES_PER_CHAT = settings.MAX_FILES_PER_CHAT
ALLOWED_UPLOAD_EXTENSIONS = {ext.lower() for ext in settings.ALLOWED_UPLOAD_EXTENSIONS}
RAG_REQUEST_TIMEOUT_SECONDS = settings.RAG_REQUEST_TIMEOUT_SECONDS
CHAT_RAG_TOP_K = settings.CHAT_RAG_TOP_K

# Regex for sanitising filenames: keep alphanumerics, hyphens, underscores, dots
_SAFE_FILENAME_RE = re.compile(r"[^\w\-.]", re.ASCII)

logger = logging.getLogger(__name__)


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
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

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


def _sanitise_filename(raw: str) -> str:
    """Strip path components and unsafe characters from a user-supplied filename."""
    # Remove any directory traversal components
    name = PurePosixPath(raw).name
    if not name:
        name = "upload"
    # Replace unsafe characters
    name = _SAFE_FILENAME_RE.sub("_", name)
    # Collapse repeated underscores and limit length
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:255] if name else "upload"


def _validate_upload_extension(filename: str) -> None:
    """Raise 415 if the file extension is not in the allow-list."""
    ext = PurePosixPath(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"File type '{ext or '(none)'}' is not allowed. "
                f"Accepted types: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            ),
        )


_extract_text = extract_text
_build_conversation_history_from_messages = build_conversation_history_from_messages
_select_rag_citations = select_rag_citations


def _build_patient_context(chat: Chat, messages: list[Message]) -> dict | None:
    return build_patient_context(chat, messages)


def _build_file_context(chat: Chat) -> str | None:
    return build_file_context(chat, extract_text_fn=_extract_text)


async def upload_file(
    db: Session,
    user: User,
    chat_id: int,
    file: UploadFile,
) -> FileAttachmentResponse:
    from src.core.chat_policy import can_upload_to_chat

    chat = chat_repository.get(db, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if not can_upload_to_chat(user, chat):
        raise HTTPException(
            status_code=403, detail="Not authorised to upload to this chat"
        )

    safe_name = _sanitise_filename(file.filename or "upload")
    _validate_upload_extension(safe_name)

    dest_dir = UPLOAD_DIR / str(chat_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE_BYTES:
        limit_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {limit_mb} MB limit ({len(contents) // 1024} KB uploaded).",
        )

    existing_count = (
        db.query(FileAttachment).filter(FileAttachment.chat_id == chat_id).count()
    )
    if existing_count >= MAX_FILES_PER_CHAT:
        raise HTTPException(
            status_code=422,
            detail=f"Chat already has {existing_count} files. Maximum is {MAX_FILES_PER_CHAT}.",
        )

    dest_path.write_bytes(contents)

    attachment = FileAttachment(
        filename=safe_name,
        file_path=str(dest_path),
        file_type=file.content_type,
        file_size=len(contents),
        chat_id=chat_id,
        uploader_id=user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    audit_repository.log(
        db,
        user_id=user.id,
        action="UPLOAD_FILE",
        details=f"Uploaded {file.filename} to chat {chat_id}",
        invalidate_admin_cache=False,
    )
    await cache.delete_pattern(
        cache_keys.chat_detail_pattern(chat_id), user_id=user.id, resource="chat_detail"
    )
    await cache.delete_pattern(
        cache_keys.chat_list_pattern(chat.user_id),
        user_id=chat.user_id,
        resource="chat_list",
    )
    await cache.delete_pattern(
        cache_keys.admin_audit_logs_pattern(), resource="admin_audit_logs"
    )
    await invalidate_chat_related_async(
        chat_id=chat_id,
        user_id=chat.user_id,
        specialty=chat.specialty,
        specialist_id=chat.specialist_id,
    )

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

    Publishes SSE lifecycle events so connected clients receive real-time
    updates.  The flow:
      1. Create a placeholder message with ``is_generating=True``.
      2. Publish ``stream_start``.
      3. Call the RAG service with streaming enabled.
      4. Publish cumulative ``content`` events as tokens arrive.
      5. Finalise the message (content, citations, ``is_generating=False``).
      6. Publish ``complete`` with citations.
      7. Close the chat's event bus so SSE clients disconnect cleanly.
    """
    async with AsyncSessionLocal() as db:
        try:
            chat = await chat_repository.async_get(db, chat_id)
            if not chat:
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
            file_context = _build_file_context(chat)

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

            rag_action = "RAG_ERROR"
            rag_details = f"query_len={len(content)} error=unknown"
            ai_content = ""
            citations = None
            try:
                if settings.INLINE_AI_TASKS:
                    try:
                        rag_response = httpx.post(
                            f"{RAG_SERVICE_URL}/answer",
                            json=rag_payload,
                            timeout=RAG_REQUEST_TIMEOUT_SECONDS,
                        )
                        rag_response.raise_for_status()
                        rag_json = rag_response.json()
                    except Exception:
                        # Compatibility for tests that patch AsyncClient.post.
                        async with httpx.AsyncClient(
                            timeout=RAG_REQUEST_TIMEOUT_SECONDS
                        ) as client:
                            rag_response = await client.post(
                                f"{RAG_SERVICE_URL}/answer",
                                json=rag_payload,
                            )
                            rag_response.raise_for_status()
                            rag_json = rag_response.json()

                    ai_content = rag_json.get("answer", "")
                    citations = _select_rag_citations(rag_json)
                else:
                    async with httpx.AsyncClient(
                        timeout=RAG_REQUEST_TIMEOUT_SECONDS
                    ) as client:
                        async with client.stream(
                            "POST",
                            f"{RAG_SERVICE_URL}/answer",
                            json=rag_payload,
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


def _on_generation_task_done(task: asyncio.Task) -> None:  # type: ignore[type-arg]
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

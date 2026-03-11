import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.db.models import ChatStatus, User
from src.db.session import AsyncSessionLocal, SessionLocal
from src.repositories import audit_repository, chat_repository, message_repository
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
)
from src.services._mappers import chat_to_response, msg_to_response
from src.utils.sse import SSEEvent, chat_event_bus


RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_chat(db: Session, user: User, data: ChatCreate) -> ChatResponse:
    chat = chat_repository.create(
        db,
        user_id=user.id,
        title=data.title,
        specialty=data.specialty,
        severity=data.severity,
    )
    audit_repository.log(
        db, user_id=user.id, action="CREATE_CHAT", details=f"Created chat: {data.title}"
    )
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
            raise HTTPException(status_code=400, detail=f"Invalid date_from: {date_from}")
    if date_to:
        try:
            parsed_date_to = datetime.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date_to: {date_to}")

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
    return [chat_to_response(c) for c in chats]


# ---------------------------------------------------------------------------
# Get (with messages)
# ---------------------------------------------------------------------------


def get_chat(db: Session, user: User, chat_id: int) -> ChatWithMessages:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    audit_repository.log(
        db, user_id=user.id, action="VIEW_CHAT", details=f"Viewed chat {chat_id}"
    )
    messages = message_repository.list_for_chat(db, chat.id)
    response = ChatWithMessages(**chat_to_response(chat).model_dump())
    response.messages = [msg_to_response(m) for m in messages]
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


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------


def _generate_ai_response_task(chat_id: int, user_id: int, content: str) -> None:
    db = SessionLocal()
    try:
        _generate_ai_response(db, chat_id, user_id, content)
    finally:
        db.close()


def _generate_ai_response(db: Session, chat_id: int, user_id: int, content: str) -> None:
    try:
        chat = chat_repository.get(db, chat_id)
        if not chat:
            return

        rag_payload = {"query": content, "top_k": 4}

        rag_action = "RAG_ERROR"
        rag_details = f"query_len={len(content)} error=unknown"
        try:
            rag_response = httpx.post(
                f"{RAG_SERVICE_URL}/answer", json=rag_payload, timeout=60
            )
            rag_response.raise_for_status()
            rag_json = rag_response.json()
            ai_content = rag_json.get("answer", "")
            citations = (
                rag_json.get("citations_used")
                or rag_json.get("citations")
                or rag_json.get("citations_retrieved")
                or None
            )
            rag_action = "RAG_ANSWER"
            rag_details = f"query_len={len(content)} top_k=4 chunks_used={len(citations) if citations else 0}"
        except Exception as exc:  # pragma: no cover - network fallback
            ai_content = (
                "RAG service unavailable right now. Echoing your question while the "
                f"service recovers: {content} (detail: {exc})"
            )
            citations = None
            rag_details = f"query_len={len(content)} error={type(exc).__name__}"

        audit_repository.log(db, user_id=user_id, action=rag_action, details=rag_details)

        message_repository.create(
            db,
            chat_id=chat.id,
            content=ai_content,
            sender="ai",
            citations=citations,
        )

        audit_repository.log(
            db,
            user_id=user_id,
            action="AI_RESPONSE_GENERATED",
            details=f"AI response generated for chat {chat_id}",
        )
    except Exception:
        db.rollback()
        raise


def send_message(
    db: Session,
    user: User,
    chat_id: int,
    content: str,
    background_tasks: BackgroundTasks,
) -> dict:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # GP can only send messages before a specialist picks up the chat
    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send messages in {chat.status.value} state",
        )

    message_repository.create(db, chat_id=chat.id, content=content, sender="user")

    if chat.status == ChatStatus.OPEN:
        chat_repository.update(db, chat, status=ChatStatus.SUBMITTED)
        audit_repository.log(
            db,
            user_id=user.id,
            action="AUTO_SUBMIT_FOR_REVIEW",
            details=f"Chat {chat_id} auto-submitted after first GP message",
        )

    if db.bind and db.bind.dialect.name == "sqlite":
        _generate_ai_response(db, chat.id, user.id, content)
    else:
        background_tasks.add_task(_generate_ai_response_task, chat.id, user.id, content)

    return {
        "status": "Message sent",
        "ai_response": f"AI response is being generated for: {content}",
        "ai_generating": True,
    }


# ---------------------------------------------------------------------------
# Async send message  (chat/RAG path — non-blocking)
# ---------------------------------------------------------------------------


async def _async_generate_ai_response(
    chat_id: int, user_id: int, content: str
) -> None:
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

            rag_payload = {"query": content, "top_k": 4, "stream": True}

            rag_action = "RAG_ERROR"
            rag_details = f"query_len={len(content)} error=unknown"
            ai_content = ""
            citations = None
            try:
                async with httpx.AsyncClient(timeout=120) as client:
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
                                citations = (
                                    chunk.get("citations_used")
                                    or chunk.get("citations")
                                    or chunk.get("citations_retrieved")
                                    or None
                                )
                            elif chunk.get("type") == "error":
                                raise RuntimeError(chunk.get("error", "RAG streaming error"))

                rag_action = "RAG_ANSWER"
                rag_details = (
                    f"query_len={len(content)} top_k=4 "
                    f"chunks_used={len(citations) if citations else 0}"
                )
            except Exception as exc:
                ai_content = (
                    "RAG service unavailable right now. Echoing your question while the "
                    f"service recovers: {content} (detail: {exc})"
                )
                citations = None
                rag_details = f"query_len={len(content)} error={type(exc).__name__}"

                # Publish error event (still finalise below)
                await chat_event_bus.publish(
                    chat_id,
                    SSEEvent(
                        event="error",
                        data={
                            "chat_id": chat_id,
                            "message_id": placeholder.id,
                            "error": str(exc),
                        },
                    ),
                )

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
            logger.exception(
                "Async AI generation failed for chat %s", chat_id
            )
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

    # Fire-and-forget async task for AI generation.
    # Under SQLite (tests) run inline so assertions can see the result.
    if db.bind.dialect.name == "sqlite":
        await _async_generate_ai_response(chat.id, user.id, content)
    else:
        asyncio.create_task(
            _async_generate_ai_response(chat.id, user.id, content)
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
    return chat_to_response(chat)

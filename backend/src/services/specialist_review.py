from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import Chat, ChatStatus, Message, NotificationType, User
from src.repositories import (
    audit_repository,
    chat_repository,
    message_repository,
    notification_repository,
)
from src.schemas.chat import ChatResponse, ReviewRequest
from src.services._mappers import chat_to_response
from src.services.cache_invalidation import (
    invalidate_admin_chat_caches_sync,
    invalidate_admin_stats_sync,
    invalidate_specialist_lists_sync,
)
from src.services.chat_service import (
    _select_rag_citations,
)
from src.services.notification_service import invalidate_notification_caches
from src.services.rag_client import build_rag_headers
from src.services.rag_context import (
    FileContextBuildResult,
    build_file_context,
    build_file_context_result,
    build_patient_context,
    extract_text,
)
from src.services.specialist_shared import (
    _build_manual_citations,
)
from src.utils.cache import cache, cache_keys
from src.utils.sse import SSEEvent, chat_event_bus

logger = logging.getLogger(__name__)

RAG_SERVICE_URL = settings.RAG_SERVICE_URL
RAG_REQUEST_TIMEOUT_SECONDS = settings.RAG_REQUEST_TIMEOUT_SECONDS
CHAT_RAG_TOP_K = settings.CHAT_RAG_TOP_K

_extract_text = extract_text
_invalidate_specialist_lists = invalidate_specialist_lists_sync
_invalidate_admin_chat_caches = invalidate_admin_chat_caches_sync
_invalidate_admin_stats_cache = invalidate_admin_stats_sync


def _build_patient_context(chat: Chat, messages: list[Message]) -> dict | None:
    return build_patient_context(chat, messages)


def _build_file_context(chat: Chat) -> str | None:
    return build_file_context(chat, extract_text_fn=_extract_text)


def _build_file_context_result(chat: Chat) -> FileContextBuildResult:
    return build_file_context_result(chat, extract_text_fn=_extract_text)


def review(
    db: Session, specialist: User, chat_id: int, body: ReviewRequest
) -> ChatResponse:
    """Process a review action on a chat.

    Validates that the chat is in ASSIGNED or REVIEWING status before
    allowing any review action. Rejects approve/reject while AI is generating.
    """
    if body.action not in (
        "approve",
        "reject",
        "request_changes",
        "manual_response",
        "send_comment",
        "unassign",
    ):
        raise HTTPException(
            status_code=400,
            detail="action must be one of: approve, reject, request_changes, manual_response, send_comment, unassign",
        )

    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.specialist_id == specialist.id)
        .first()
    )
    if not chat:
        raise HTTPException(
            status_code=404, detail="Chat not found or not assigned to you"
        )

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Chat must be ASSIGNED or REVIEWING to review (current: {chat.status.value})",
        )

    if body.action in ("approve", "reject", "manual_response", "unassign"):
        generating = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.sender == "ai",
                Message.is_generating,
            )
            .first()
        )
        if generating:
            raise HTTPException(
                status_code=400,
                detail="Cannot perform this action while an AI response is being generated",
            )

    if body.action == "send_comment":
        if not body.feedback or not body.feedback.strip():
            raise HTTPException(
                status_code=400,
                detail="feedback is required for send_comment action",
            )
        message_repository.create(
            db,
            chat_id=chat.id,
            content=body.feedback.strip(),
            sender="specialist",
        )
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="SPECIALIST_COMMENT",
            details=f"Specialist sent comment to GP in chat {chat_id}",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=NotificationType.SPECIALIST_MSG,
            title="New comment from specialist",
            body=f"{specialist.full_name or specialist.email} left a comment on '{chat.title}'.",
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)
        _invalidate_chat_views(chat, specialist.id)
        return chat_to_response(chat)

    if body.action == "unassign":
        old_specialist_id = chat.specialist_id
        chat = chat_repository.update(
            db,
            chat,
            status=ChatStatus.SUBMITTED,
            specialist_id=None,
            assigned_at=None,
        )
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="SPECIALIST_UNASSIGN",
            details=f"Specialist unassigned from chat {chat_id}",
        )
        _invalidate_chat_views(chat, old_specialist_id)
        return chat_to_response(chat)

    if body.action == "manual_response":
        if not body.replacement_content or not body.replacement_content.strip():
            raise HTTPException(
                status_code=400,
                detail="replacement_content is required for manual_response action",
            )
        _mark_last_ai_message(db, chat.id, body)
        replacement_content = body.replacement_content.strip()
        message_repository.create(
            db,
            chat_id=chat.id,
            content=replacement_content,
            sender="specialist",
            citations=_build_manual_citations(body.replacement_sources),
        )
        chat = chat_repository.update(
            db,
            chat,
            status=ChatStatus.APPROVED,
            reviewed_at=datetime.now(timezone.utc),
            review_feedback=body.feedback,
        )
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="REVIEW_MANUAL_RESPONSE",
            details=f"Chat {chat_id} closed with manual response by specialist",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=NotificationType.CHAT_APPROVED,
            title="Specialist provided a response",
            body=(
                f"{specialist.full_name or specialist.email} responded to '{chat.title}'."
            ),
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)
        _invalidate_chat_views(chat, specialist.id)
        return chat_to_response(chat)

    _mark_last_ai_message(db, chat.id, body)

    if body.action == "request_changes":
        _regenerate_ai_response(db, chat, body.feedback)
        chat = chat_repository.update(
            db,
            chat,
            status=ChatStatus.REVIEWING,
            review_feedback=body.feedback,
        )
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="REVIEW_REQUEST_CHANGES",
            details=f"Chat {chat_id} revision requested. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=NotificationType.CHAT_REVISION,
            title="AI response is being revised",
            body=(
                f"A specialist is iterating on the AI response for '{chat.title}'. "
                f"Feedback: {body.feedback or 'none'}"
            ),
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)
    else:
        new_status = (
            ChatStatus.APPROVED if body.action == "approve" else ChatStatus.REJECTED
        )
        chat = chat_repository.update(
            db,
            chat,
            status=new_status,
            reviewed_at=datetime.now(timezone.utc),
            review_feedback=body.feedback,
        )
        audit_action = "REVIEW_APPROVE" if body.action == "approve" else "REVIEW_REJECT"
        audit_repository.log(
            db,
            user_id=specialist.id,
            action=audit_action,
            details=f"Chat {chat_id} {body.action}d. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=(
                NotificationType.CHAT_APPROVED
                if body.action == "approve"
                else NotificationType.CHAT_REJECTED
            ),
            title="Chat approved" if body.action == "approve" else "Chat rejected",
            body=(
                f"Your chat '{chat.title}' was approved by {specialist.full_name or specialist.email}."
                if body.action == "approve"
                else f"Your chat '{chat.title}' was rejected. Feedback: {body.feedback or 'none'}"
            ),
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)

    _invalidate_chat_views(chat, specialist.id)
    return chat_to_response(chat)


def review_message(
    db: Session,
    specialist: User,
    chat_id: int,
    message_id: int,
    body: ReviewRequest,
) -> ChatResponse:
    """Review a specific AI message within a chat.

    Validates chat is in ASSIGNED or REVIEWING status before proceeding.
    """
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.specialist_id == specialist.id)
        .first()
    )
    if not chat:
        raise HTTPException(
            status_code=404, detail="Chat not found or not assigned to you"
        )

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Chat must be ASSIGNED or REVIEWING to review (current: {chat.status.value})",
        )

    target = (
        db.query(Message)
        .filter(
            Message.id == message_id,
            Message.chat_id == chat_id,
            Message.sender == "ai",
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="AI message not found in this chat")

    if body.action == "manual_response" and (
        not body.replacement_content or not body.replacement_content.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="replacement_content is required for manual_response action",
        )

    if body.action == "edit_response" and (
        not body.edited_content or not body.edited_content.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="edited_content is required for edit_response action",
        )

    _mark_message(db, target, body)

    if body.action == "request_changes":
        _regenerate_ai_response(db, chat, body.feedback)
        chat = chat_repository.update(
            db,
            chat,
            status=ChatStatus.REVIEWING,
            review_feedback=body.feedback,
        )
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="REVIEW_REQUEST_CHANGES",
            details=f"Chat {chat_id} msg {message_id} revision requested. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=NotificationType.CHAT_REVISION,
            title="AI response is being revised",
            body=(
                f"A specialist is iterating on the AI response for '{chat.title}'. "
                f"Feedback: {body.feedback or 'none'}"
            ),
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)
    elif body.action == "edit_response":
        edited_content = (
            body.edited_content.strip() if body.edited_content is not None else ""
        )
        target.content = edited_content
        target.review_status = "edited"
        target.review_feedback = body.feedback
        target.reviewed_at = datetime.now(timezone.utc)
        if body.replacement_sources:
            target.citations = _build_manual_citations(body.replacement_sources)
        db.commit()
        db.refresh(target)
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="REVIEW_EDIT_RESPONSE",
            details=f"Chat {chat_id} msg {message_id} edited by specialist. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=NotificationType.SPECIALIST_MSG,
            title="Specialist edited the AI response",
            body=(
                f"{specialist.full_name or specialist.email} edited an AI response "
                f"in '{chat.title}'."
            ),
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)
        if chat.status != ChatStatus.REVIEWING:
            chat = chat_repository.update(db, chat, status=ChatStatus.REVIEWING)
    elif body.action == "manual_response":
        replacement_content = (
            body.replacement_content.strip()
            if body.replacement_content is not None
            else ""
        )
        message_repository.create(
            db,
            chat_id=chat.id,
            content=replacement_content,
            sender="specialist",
            citations=_build_manual_citations(body.replacement_sources),
        )
        audit_repository.log(
            db,
            user_id=specialist.id,
            action="REVIEW_MANUAL_RESPONSE",
            details=f"Chat {chat_id} msg {message_id} replaced with manual response. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db,
            user_id=chat.user_id,
            type=NotificationType.SPECIALIST_MSG,
            title="Specialist provided a manual response",
            body=(
                f"{specialist.full_name or specialist.email} replaced an AI response "
                f"with a manual answer in '{chat.title}'."
            ),
            chat_id=chat.id,
        )
        invalidate_notification_caches(chat.user_id)
        if chat.status != ChatStatus.REVIEWING:
            chat = chat_repository.update(db, chat, status=ChatStatus.REVIEWING)
    else:
        audit_action = "REVIEW_APPROVE" if body.action == "approve" else "REVIEW_REJECT"
        audit_repository.log(
            db,
            user_id=specialist.id,
            action=audit_action,
            details=f"Chat {chat_id} msg {message_id} {body.action}d. Feedback: {body.feedback or 'none'}",
        )
        if chat.status != ChatStatus.REVIEWING:
            chat = chat_repository.update(db, chat, status=ChatStatus.REVIEWING)

    _invalidate_chat_views(chat, specialist.id)
    return chat_to_response(chat)


def send_message(db: Session, specialist: User, chat_id: int, content: str) -> dict:
    """Send a specialist message in a chat. Content is pre-validated by MessageCreate schema."""
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.specialist_id == specialist.id)
        .first()
    )
    if not chat:
        raise HTTPException(
            status_code=404, detail="Chat not found or not assigned to you"
        )

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Can only message ASSIGNED or REVIEWING chats (current: {chat.status.value})",
        )

    if chat.status == ChatStatus.ASSIGNED:
        chat_repository.update(db, chat, status=ChatStatus.REVIEWING)

    msg = message_repository.create(
        db, chat_id=chat.id, content=content, sender="specialist"
    )
    audit_repository.log(
        db,
        user_id=specialist.id,
        action="SPECIALIST_MESSAGE",
        details=f"Specialist sent message in chat {chat_id}",
    )
    notification_repository.create(
        db,
        user_id=chat.user_id,
        type=NotificationType.SPECIALIST_MSG,
        title="New message from specialist",
        body=f"{specialist.full_name or specialist.email} sent a message in '{chat.title}'.",
        chat_id=chat.id,
    )
    invalidate_notification_caches(chat.user_id)
    _invalidate_chat_views(chat, specialist.id)
    return {"status": "Message sent", "message_id": msg.id}


def _invalidate_chat_views(chat: Chat, specialist_id: int | None) -> None:
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat.id),
        user_id=specialist_id,
        resource="chat_detail",
    )
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat.id),
        user_id=chat.user_id,
        resource="chat_detail",
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(chat.user_id),
        user_id=chat.user_id,
        resource="chat_list",
    )
    _invalidate_specialist_lists(
        specialty=chat.specialty,
        specialist_id=specialist_id,
    )
    _invalidate_admin_chat_caches(chat.id)
    _invalidate_admin_stats_cache()


def _mark_message(db: Session, msg: Message, body: ReviewRequest) -> None:
    if body.action == "approve":
        msg.review_status = "approved"
    elif body.action == "manual_response":
        msg.review_status = "replaced"
    elif body.action == "edit_response":
        msg.review_status = "edited"
    else:
        msg.review_status = "rejected"
    msg.review_feedback = body.feedback
    msg.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(msg)


def _mark_last_ai_message(db: Session, chat_id: int, body: ReviewRequest) -> None:
    last_ai = (
        db.query(Message)
        .filter(
            Message.chat_id == chat_id,
            Message.sender == "ai",
            Message.review_status.is_(None),
        )
        .order_by(Message.created_at.desc())
        .first()
    )
    if last_ai:
        _mark_message(db, last_ai, body)


def _regenerate_ai_response(
    db: Session, chat: Chat, feedback: Optional[str]
) -> Message:
    """Request a revised AI response via the RAG service and publish SSE events."""
    messages = message_repository.list_for_chat(db, chat.id)
    user_messages = [m for m in messages if m.sender == "user"]
    ai_messages = [m for m in messages if m.sender == "ai"]

    original_query = user_messages[-1].content if user_messages else "consultation"
    previous_answer = ai_messages[-1].content if ai_messages else ""
    patient_context = _build_patient_context(chat, messages)
    file_context_result = _build_file_context_result(chat)
    file_context = file_context_result.file_context

    placeholder = message_repository.create(
        db,
        chat_id=chat.id,
        content="Revising response based on specialist feedback…",
        sender="ai",
        citations=[],
        is_generating=True,
    )

    _do_revise(
        db,
        placeholder,
        original_query or "",
        previous_answer or "",
        feedback or "",
        chat.specialty,
        chat.severity,
        patient_context,
        file_context,
        file_context_result.was_truncated,
    )

    return placeholder


def _do_revise(
    db: Session,
    placeholder: Message,
    original_query: str,
    previous_answer: str,
    feedback: str,
    specialty: str | None,
    severity: str | None,
    patient_context: dict | None,
    file_context: str | None,
    file_context_truncated: bool,
) -> None:
    """Call the RAG /revise endpoint, update the placeholder, and emit SSE events."""
    revision_failed = False
    rag_payload = {
        "original_query": original_query,
        "previous_answer": previous_answer,
        "feedback": feedback,
        "top_k": CHAT_RAG_TOP_K,
        "specialty": specialty,
        "severity": severity,
        "patient_context": patient_context,
        "file_context": file_context,
        "file_context_truncated": file_context_truncated,
    }

    try:
        rag_headers = build_rag_headers()
        request_kwargs: dict[str, Any] = {}
        if rag_headers:
            request_kwargs["headers"] = rag_headers
        with httpx.Client(timeout=RAG_REQUEST_TIMEOUT_SECONDS) as client:
            rag_response = client.post(
                f"{RAG_SERVICE_URL}/revise",
                json=rag_payload,
                **request_kwargs,
            )
        rag_response.raise_for_status()
        rag_json = rag_response.json()
        if not isinstance(rag_json, dict):
            raise ValueError(
                f"Expected dict from RAG /revise, got {type(rag_json).__name__}"
            )
        revised_content = rag_json.get("answer", "")
        if not isinstance(revised_content, str):
            raise ValueError(
                f"Expected 'answer' string from RAG, got {type(revised_content).__name__}"
            )
        citations = _select_rag_citations(rag_json) or []
    except Exception as exc:
        logger.warning("RAG /revise failed for chat %s: %s", placeholder.chat_id, exc)
        revision_failed = True
        revised_content = (
            "The clinical knowledge service is temporarily unavailable for revision. "
            "Please try again shortly."
        )
        citations = []

    placeholder.content = revised_content
    placeholder.citations = citations
    placeholder.is_generating = False
    db.commit()
    db.refresh(placeholder)

    # Publish SSE events so connected clients receive the revised response
    chat_event_bus.publish_threadsafe(
        placeholder.chat_id,
        SSEEvent(
            event="content",
            data={
                "chat_id": placeholder.chat_id,
                "message_id": placeholder.id,
                "content": revised_content,
            },
        ),
    )
    chat_event_bus.publish_threadsafe(
        placeholder.chat_id,
        SSEEvent(
            event="complete",
            data={
                "chat_id": placeholder.chat_id,
                "message_id": placeholder.id,
                "content": revised_content,
                "citations": citations,
            },
        ),
    )
    chat_event_bus.close_chat_threadsafe(placeholder.chat_id)

    chat = db.query(Chat).filter(Chat.id == placeholder.chat_id).first()

    if chat:
        _invalidate_chat_views(chat, chat.specialist_id)
        if revision_failed:
            notification_repository.create(
                db,
                user_id=chat.user_id,
                type=NotificationType.CHAT_REVISION,
                title="Revision needs retry",
                body=(
                    "A specialist requested a revision, but the knowledge service was "
                    "temporarily unavailable. Please retry shortly."
                ),
                chat_id=chat.id,
            )
            invalidate_notification_caches(chat.user_id)
    else:
        _invalidate_admin_chat_caches(placeholder.chat_id)
        _invalidate_admin_stats_cache()

    try:
        if chat and chat.specialist_id is not None:
            audit_repository.log(
                db,
                user_id=chat.specialist_id,
                action="RAG_ERROR" if revision_failed else "RAG_REVISE",
                details=f"chunks_used={len(citations)}",
            )
    except Exception:
        logger.exception(
            "Failed to write specialist revision audit log for chat %s",
            placeholder.chat_id,
        )

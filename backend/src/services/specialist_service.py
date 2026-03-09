from datetime import datetime
from typing import Optional
import os

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.db.models import Chat, ChatStatus, Message, NotificationType, User
from src.db.session import SessionLocal
from src.repositories import (
    audit_repository,
    chat_repository,
    message_repository,
    notification_repository,
)
from src.schemas.chat import AssignRequest, ChatResponse, ChatWithMessages, ReviewRequest
from src.services._mappers import chat_to_response, msg_to_response


RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001")
RAG_REQUEST_TIMEOUT_SECONDS = float(os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "120"))


def get_queue(db: Session, specialist: User) -> list[ChatResponse]:
    query = db.query(Chat).filter(Chat.status == ChatStatus.SUBMITTED)
    if specialist.specialty:
        query = query.filter(Chat.specialty == specialist.specialty)
    chats = query.order_by(Chat.created_at.asc()).all()
    return [chat_to_response(c) for c in chats]


def get_assigned(db: Session, specialist: User) -> list[ChatResponse]:
    chats = (
        db.query(Chat)
        .filter(
            Chat.specialist_id == specialist.id,
            Chat.status.in_([ChatStatus.ASSIGNED, ChatStatus.REVIEWING]),
        )
        .order_by(Chat.assigned_at.asc())
        .all()
    )
    return [chat_to_response(c) for c in chats]


def get_chat_detail(db: Session, specialist: User, chat_id: int) -> ChatWithMessages:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    in_queue = chat.status == ChatStatus.SUBMITTED and (
        not specialist.specialty or chat.specialty == specialist.specialty
    )
    assigned_to_me = chat.specialist_id == specialist.id

    if not (in_queue or assigned_to_me):
        raise HTTPException(status_code=403, detail="You do not have access to this chat")

    messages = message_repository.list_for_chat(db, chat.id)
    resp = ChatWithMessages(**chat_to_response(chat).model_dump())
    resp.messages = [msg_to_response(m) for m in messages]
    return resp


def assign(db: Session, specialist: User, chat_id: int, body: AssignRequest) -> ChatResponse:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"Chat is not in SUBMITTED state (current: {chat.status.value})",
        )
    if body.specialist_id != specialist.id:
        raise HTTPException(status_code=403, detail="You can only assign yourself to a chat")

    # Verify specialty match
    if specialist.specialty and chat.specialty and specialist.specialty != chat.specialty:
        raise HTTPException(
            status_code=403,
            detail=f"Your specialty ({specialist.specialty}) does not match this chat's specialty ({chat.specialty})",
        )

    chat = chat_repository.update(
        db, chat,
        specialist_id=specialist.id,
        status=ChatStatus.ASSIGNED,
        assigned_at=datetime.utcnow(),
    )
    audit_repository.log(
        db, user_id=specialist.id, action="ASSIGN_SPECIALIST",
        details=f"Specialist #{specialist.id} assigned to chat {chat_id}",
    )
    notification_repository.create(
        db,
        user_id=chat.user_id,
        type=NotificationType.CHAT_ASSIGNED,
        title="Chat assigned to a specialist",
        body=f"Your chat '{chat.title}' has been picked up by {specialist.full_name or specialist.email}.",
        chat_id=chat.id,
    )
    return chat_to_response(chat)


def review(db: Session, specialist: User, chat_id: int, body: ReviewRequest) -> ChatResponse:
    if body.action not in ("approve", "reject", "request_changes"):
        raise HTTPException(
            status_code=400,
            detail="action must be 'approve', 'reject', or 'request_changes' (use per-message review for 'manual_response')",
        )

    chat = db.query(Chat).filter(
        Chat.id == chat_id, Chat.specialist_id == specialist.id
    ).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or not assigned to you")

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Chat must be ASSIGNED or REVIEWING to review (current: {chat.status.value})",
        )

    # Block approve/reject while any AI message is still being generated
    if body.action in ("approve", "reject"):
        generating = db.query(Message).filter(
            Message.chat_id == chat_id,
            Message.sender == "ai",
            Message.is_generating == True,
        ).first()
        if generating:
            raise HTTPException(
                status_code=400,
                detail="Cannot close the chat while an AI response is being generated",
            )

    # Mark the latest AI message with the review outcome
    _mark_last_ai_message(db, chat.id, body)

    if body.action == "request_changes":
        # Regenerate AI response and keep the chat active for continued review
        _regenerate_ai_response(db, chat, body.feedback)
        chat = chat_repository.update(
            db, chat,
            status=ChatStatus.REVIEWING,
            review_feedback=body.feedback,
        )
        audit_repository.log(
            db, user_id=specialist.id,
            action="REVIEW_REQUEST_CHANGES",
            details=f"Chat {chat_id} revision requested. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db, user_id=chat.user_id,
            type=NotificationType.CHAT_REVISION,
            title="AI response is being revised",
            body=(
                f"A specialist is iterating on the AI response for '{chat.title}'. "
                f"Feedback: {body.feedback or 'none'}"
            ),
            chat_id=chat.id,
        )
    else:
        # approve or reject → terminal state
        new_status = ChatStatus.APPROVED if body.action == "approve" else ChatStatus.REJECTED
        chat = chat_repository.update(
            db, chat,
            status=new_status,
            reviewed_at=datetime.utcnow(),
            review_feedback=body.feedback,
        )
        audit_action = "REVIEW_APPROVE" if body.action == "approve" else "REVIEW_REJECT"
        audit_repository.log(
            db, user_id=specialist.id,
            action=audit_action,
            details=f"Chat {chat_id} {body.action}d. Feedback: {body.feedback or 'none'}",
        )
        if body.action == "approve":
            notification_repository.create(
                db, user_id=chat.user_id,
                type=NotificationType.CHAT_APPROVED,
                title="Chat approved",
                body=f"Your chat '{chat.title}' was approved by {specialist.full_name or specialist.email}.",
                chat_id=chat.id,
            )
        else:
            notification_repository.create(
                db, user_id=chat.user_id,
                type=NotificationType.CHAT_REJECTED,
                title="Chat rejected",
                body=f"Your chat '{chat.title}' was rejected. Feedback: {body.feedback or 'none'}",
                chat_id=chat.id,
            )

    return chat_to_response(chat)


def review_message(
    db: Session, specialist: User, chat_id: int, message_id: int, body: ReviewRequest,
) -> ChatResponse:
    """Review a specific AI message."""
    if body.action not in ("approve", "reject", "request_changes", "manual_response"):
        raise HTTPException(
            status_code=400,
            detail="action must be 'approve', 'reject', 'request_changes', or 'manual_response'",
        )

    chat = db.query(Chat).filter(
        Chat.id == chat_id, Chat.specialist_id == specialist.id
    ).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or not assigned to you")

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Chat must be ASSIGNED or REVIEWING to review (current: {chat.status.value})",
        )

    # Find and validate the target message
    target = db.query(Message).filter(
        Message.id == message_id, Message.chat_id == chat_id, Message.sender == "ai",
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="AI message not found in this chat")

    # Validate manual_response has replacement content before making any changes
    if body.action == "manual_response":
        if not body.replacement_content or not body.replacement_content.strip():
            raise HTTPException(
                status_code=400,
                detail="replacement_content is required for manual_response action",
            )

    # Mark the specific message
    _mark_message(db, target, body)

    if body.action == "request_changes":
        _regenerate_ai_response(db, chat, body.feedback)
        chat = chat_repository.update(
            db, chat,
            status=ChatStatus.REVIEWING,
            review_feedback=body.feedback,
        )
        audit_repository.log(
            db, user_id=specialist.id,
            action="REVIEW_REQUEST_CHANGES",
            details=f"Chat {chat_id} msg {message_id} revision requested. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db, user_id=chat.user_id,
            type=NotificationType.CHAT_REVISION,
            title="AI response is being revised",
            body=(
                f"A specialist is iterating on the AI response for '{chat.title}'. "
                f"Feedback: {body.feedback or 'none'}"
            ),
            chat_id=chat.id,
        )
    elif body.action == "manual_response":
        # Reject the AI message without regeneration; specialist provides replacement
        # Send the specialist's replacement as a specialist message
        message_repository.create(
            db, chat_id=chat.id, content=body.replacement_content.strip(), sender="specialist",
        )
        audit_repository.log(
            db, user_id=specialist.id,
            action="REVIEW_MANUAL_RESPONSE",
            details=f"Chat {chat_id} msg {message_id} replaced with manual response. Feedback: {body.feedback or 'none'}",
        )
        notification_repository.create(
            db, user_id=chat.user_id,
            type=NotificationType.SPECIALIST_MSG,
            title="Specialist provided a manual response",
            body=(
                f"{specialist.full_name or specialist.email} replaced an AI response "
                f"with a manual answer in '{chat.title}'."
            ),
            chat_id=chat.id,
        )
        # Ensure status is REVIEWING
        if chat.status != ChatStatus.REVIEWING:
            chat = chat_repository.update(db, chat, status=ChatStatus.REVIEWING)
    else:
        # approve or reject for this message
        audit_action = "REVIEW_APPROVE" if body.action == "approve" else "REVIEW_REJECT"
        audit_repository.log(
            db, user_id=specialist.id,
            action=audit_action,
            details=f"Chat {chat_id} msg {message_id} {body.action}d. Feedback: {body.feedback or 'none'}",
        )

        # Ensure status is REVIEWING
        if chat.status != ChatStatus.REVIEWING:
            chat = chat_repository.update(db, chat, status=ChatStatus.REVIEWING)

    return chat_to_response(chat)


def _mark_message(db: Session, msg: Message, body: ReviewRequest) -> None:
    """Mark a specific AI message with the specialist's review outcome."""
    if body.action == "approve":
        msg.review_status = "approved"
    elif body.action == "manual_response":
        msg.review_status = "replaced"
    else:
        msg.review_status = "rejected"
    msg.review_feedback = body.feedback
    msg.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)


def _mark_last_ai_message(db: Session, chat_id: int, body: ReviewRequest) -> None:
    """Mark the most recent *unreviewed* AI message with the specialist's review outcome."""
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


def _regenerate_ai_response(db: Session, chat: Chat, feedback: Optional[str]) -> Message:
    """Create a placeholder AI message and kick off a RAG revision.

    When the database is SQLite (i.e. test / dev mode) the revision runs
    synchronously so the caller sees the result immediately.  Otherwise a
    background thread is spawned (matching the pattern used for initial AI
    answers in chat_service).
    """
    messages = message_repository.list_for_chat(db, chat.id)
    user_messages = [m for m in messages if m.sender == "user"]
    ai_messages = [m for m in messages if m.sender == "ai"]

    original_query = user_messages[-1].content if user_messages else "consultation"
    previous_answer = ai_messages[-1].content if ai_messages else ""

    # Create a temporary placeholder message so the specialist sees immediate
    # feedback (matches the "ai_generating" pattern used for initial answers).
    placeholder = message_repository.create(
        db,
        chat_id=chat.id,
        content="Revising response based on specialist feedback…",
        sender="ai",
        citations=[],        is_generating=True,    )

    is_sqlite = db.bind and db.bind.dialect.name == "sqlite"

    if is_sqlite:
        # Run synchronously (tests use in-memory SQLite with a single connection).
        _do_revise(
            db,
            placeholder,
            original_query,
            previous_answer,
            feedback or "",
            chat.specialty,
            chat.severity,
        )
    else:
        import threading
        thread = threading.Thread(
            target=_regenerate_ai_response_task,
            args=(
                placeholder.id,
                original_query,
                previous_answer,
                feedback or "",
                chat.specialty,
                chat.severity,
            ),
            daemon=True,
        )
        thread.start()

    return placeholder


def _do_revise(
    db: Session,
    placeholder: Message,
    original_query: str,
    previous_answer: str,
    feedback: str,
    specialty: str | None,
    severity: str | None,
) -> None:
    """Call the RAG /revise endpoint and update the placeholder message in-place."""
    rag_payload = {
        "original_query": original_query,
        "previous_answer": previous_answer,
        "feedback": feedback,
        "top_k": 4,
        "specialty": specialty,
        "severity": severity,
    }

    try:
        rag_response = httpx.post(
            f"{RAG_SERVICE_URL}/revise",
            json=rag_payload,
            timeout=RAG_REQUEST_TIMEOUT_SECONDS,
        )
        rag_response.raise_for_status()
        rag_json = rag_response.json()
        revised_content = rag_json.get("answer", "")
        citations = rag_json.get("citations", [])
    except Exception as exc:  # pragma: no cover - network fallback
        revised_content = (
            f"[Revised after specialist feedback: {feedback}] "
            f"RAG service unavailable — original question: {original_query} "
            f"(detail: {exc})"
        )
        citations = []

    placeholder.content = revised_content
    placeholder.citations = citations
    placeholder.is_generating = False
    db.commit()
    db.refresh(placeholder)

    try:
        chat = db.query(Chat).filter(Chat.id == placeholder.chat_id).first()
        audit_repository.log(
            db,
            user_id=chat.specialist_id if chat else None,
            action="RAG_REVISE" if revised_content else "RAG_ERROR",
            details=f"chunks_used={len(citations)}",
        )
    except Exception:
        pass


def _regenerate_ai_response_task(
    placeholder_id: int,
    original_query: str,
    previous_answer: str,
    feedback: str,
    specialty: str | None,
    severity: str | None,
) -> None:
    """Background task: call the RAG /revise endpoint and update the placeholder message."""
    db = SessionLocal()
    try:
        placeholder = db.query(Message).filter(Message.id == placeholder_id).first()
        if placeholder:
            _do_revise(
                db,
                placeholder,
                original_query,
                previous_answer,
                feedback,
                specialty,
                severity,
            )
    except Exception:
        db.rollback()
    finally:
        db.close()


def send_message(db: Session, specialist: User, chat_id: int, content: str) -> dict:
    chat = db.query(Chat).filter(
        Chat.id == chat_id, Chat.specialist_id == specialist.id
    ).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or not assigned to you")

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Can only message ASSIGNED or REVIEWING chats (current: {chat.status.value})",
        )

    # Move to REVIEWING when specialist first engages
    if chat.status == ChatStatus.ASSIGNED:
        chat_repository.update(db, chat, status=ChatStatus.REVIEWING)

    msg = message_repository.create(
        db, chat_id=chat.id, content=content, sender="specialist"
    )
    audit_repository.log(
        db, user_id=specialist.id, action="SPECIALIST_MESSAGE",
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
    return {"status": "Message sent", "message_id": msg.id}

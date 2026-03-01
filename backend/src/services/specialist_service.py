from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.db.models import Chat, ChatStatus, Message, NotificationType, User
from src.repositories import (
    audit_repository,
    chat_repository,
    message_repository,
    notification_repository,
)
from src.schemas.chat import AssignRequest, ChatResponse, ChatWithMessages, ReviewRequest
from src.services._mappers import chat_to_response, msg_to_response


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
        details=f"Specialist {specialist.email} assigned to chat {chat_id}",
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
            detail="action must be 'approve', 'reject', or 'request_changes'",
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
    """Review a specific AI message. Auto-approve the chat when all AI messages are reviewed."""
    if body.action not in ("approve", "reject", "request_changes"):
        raise HTTPException(
            status_code=400,
            detail="action must be 'approve', 'reject', or 'request_changes'",
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
    else:
        # approve or reject for this message — check if all AI messages are now reviewed
        audit_action = "REVIEW_APPROVE" if body.action == "approve" else "REVIEW_REJECT"
        audit_repository.log(
            db, user_id=specialist.id,
            action=audit_action,
            details=f"Chat {chat_id} msg {message_id} {body.action}d. Feedback: {body.feedback or 'none'}",
        )

        unreviewed_count = (
            db.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.sender == "ai",
                Message.review_status.is_(None),
            )
            .count()
        )

        if unreviewed_count == 0:
            # All AI messages have been reviewed → approve the consultation
            chat = chat_repository.update(
                db, chat,
                status=ChatStatus.APPROVED,
                reviewed_at=datetime.utcnow(),
                review_feedback=body.feedback,
            )
            notification_repository.create(
                db, user_id=chat.user_id,
                type=NotificationType.CHAT_APPROVED,
                title="Chat approved",
                body=f"Your chat '{chat.title}' was approved by {specialist.full_name or specialist.email}.",
                chat_id=chat.id,
            )
        else:
            # Still messages to review — ensure status is REVIEWING
            if chat.status != ChatStatus.REVIEWING:
                chat = chat_repository.update(db, chat, status=ChatStatus.REVIEWING)

    return chat_to_response(chat)


def _mark_message(db: Session, msg: Message, body: ReviewRequest) -> None:
    """Mark a specific AI message with the specialist's review outcome."""
    msg.review_status = "approved" if body.action == "approve" else "rejected"
    msg.review_feedback = body.feedback
    msg.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)


def _mark_last_ai_message(db: Session, chat_id: int, body: ReviewRequest) -> None:
    """Mark the most recent AI message with the specialist's review outcome."""
    last_ai = (
        db.query(Message)
        .filter(Message.chat_id == chat_id, Message.sender == "ai")
        .order_by(Message.created_at.desc())
        .first()
    )
    if last_ai:
        _mark_message(db, last_ai, body)


def _regenerate_ai_response(db: Session, chat: Chat, feedback: Optional[str]) -> Message:
    """Generate a new AI response incorporating the specialist's feedback."""
    messages = message_repository.list_for_chat(db, chat.id)
    user_messages = [m for m in messages if m.sender == "user"]
    last_user_content = user_messages[-1].content if user_messages else "consultation"

    new_content = (
        f"[Revised after specialist feedback: {feedback or 'none'}] "
        f"I received: {last_user_content}"
    )
    return message_repository.create(
        db,
        chat_id=chat.id,
        content=new_content,
        sender="ai",
        citations=[],
    )


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

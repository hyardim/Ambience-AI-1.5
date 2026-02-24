from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.db.models import Chat, ChatStatus, NotificationType, User
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
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

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

    new_status = ChatStatus.APPROVED if body.action == "approve" else ChatStatus.REJECTED
    chat = chat_repository.update(
        db, chat,
        status=new_status,
        reviewed_at=datetime.utcnow(),
        review_feedback=body.feedback,
    )
    audit_repository.log(
        db, user_id=specialist.id,
        action=f"REVIEW_{body.action.upper()}",
        details=f"Chat {chat_id} {body.action}d. Feedback: {body.feedback or 'none'}",
    )
    notif_type = NotificationType.CHAT_APPROVED if body.action == "approve" else NotificationType.CHAT_REJECTED
    notif_title = "Chat approved" if body.action == "approve" else "Chat returned with feedback"
    notif_body = (
        f"Your chat '{chat.title}' was approved by {specialist.full_name or specialist.email}."
        if body.action == "approve"
        else f"Your chat '{chat.title}' was rejected. Feedback: {body.feedback or 'none'}"
    )
    notification_repository.create(
        db, user_id=chat.user_id,
        type=notif_type, title=notif_title, body=notif_body, chat_id=chat.id,
    )
    return chat_to_response(chat)


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

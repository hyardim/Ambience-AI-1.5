from typing import Optional
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.db.models import AuditLog, Chat, ChatStatus, User, UserRole
from src.repositories import audit_repository, chat_repository, message_repository, user_repository
from src.schemas.auth import UserOut
from src.schemas.chat import ChatUpdate, ChatWithMessages
from src.services._mappers import chat_to_response, msg_to_response


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

class UserUpdateAdmin:
    def __init__(
        self,
        full_name: Optional[str] = None,
        specialty: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ):
        self.full_name = full_name
        self.specialty = specialty
        self.role = role
        self.is_active = is_active


def list_users(db: Session, role: Optional[str] = None) -> list[UserOut]:
    query = db.query(User)
    if role:
        try:
            query = query.filter(User.role == UserRole(role))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
    users = query.order_by(User.id).all()
    return [UserOut.model_validate(u) for u in users]


def get_user(db: Session, user_id: int) -> UserOut:
    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(user)


def update_user(db: Session, user_id: int, payload: UserUpdateAdmin) -> UserOut:
    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    fields: dict = {}
    if payload.full_name is not None:
        fields["full_name"] = payload.full_name
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty
    if payload.is_active is not None:
        fields["is_active"] = payload.is_active
    if payload.role is not None:
        try:
            fields["role"] = UserRole(payload.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")

    user = user_repository.update(db, user, **fields)
    return UserOut.model_validate(user)


def deactivate_user(db: Session, user_id: int) -> UserOut:
    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user = user_repository.update(db, user, is_active=False)
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# Chat management
# ---------------------------------------------------------------------------

def list_all_chats(
    db: Session,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    user_id: Optional[int] = None,
    specialist_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[dict]:
    query = db.query(Chat)
    if status:
        try:
            query = query.filter(Chat.status == ChatStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if specialty:
        query = query.filter(Chat.specialty == specialty)
    if user_id:
        query = query.filter(Chat.user_id == user_id)
    if specialist_id:
        query = query.filter(Chat.specialist_id == specialist_id)

    chats = query.order_by(Chat.created_at.desc()).offset(skip).limit(limit).all()

    result = []
    for c in chats:
        entry = chat_to_response(c).model_dump()
        entry["owner_name"] = c.owner.full_name if c.owner else None
        entry["specialist_name"] = c.specialist.full_name if c.specialist else None
        result.append(entry)
    return result


def get_any_chat(db: Session, chat_id: int) -> ChatWithMessages:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = message_repository.list_for_chat(db, chat.id)
    resp = ChatWithMessages(**chat_to_response(chat).model_dump())
    resp.messages = [msg_to_response(m) for m in messages]
    return resp


def update_any_chat(db: Session, chat_id: int, payload: ChatUpdate) -> dict:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

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
            raise HTTPException(status_code=400, detail=f"Invalid status: {payload.status}")

    chat = chat_repository.update(db, chat, **fields)
    entry = chat_to_response(chat).model_dump()
    entry["owner_name"] = chat.owner.full_name if chat.owner else None
    entry["specialist_name"] = chat.specialist.full_name if chat.specialist else None
    return entry


def delete_any_chat(db: Session, chat_id: int) -> None:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat_repository.delete(db, chat)


# ---------------------------------------------------------------------------
# Audit log viewing
# ---------------------------------------------------------------------------

def list_audit_logs(
    db: Session,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 200,
) -> list[dict]:
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action.upper())
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)

    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "user_email": log.user.email if log.user else None,
            "action": log.action,
            "details": log.details,
            "timestamp": log.timestamp,
        }
        for log in logs
    ]

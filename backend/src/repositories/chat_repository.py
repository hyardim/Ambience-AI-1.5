from typing import Optional
from sqlalchemy.orm import Session

from src.db.models import Chat, ChatStatus


def get(
    db: Session,
    chat_id: int,
    user_id: Optional[int] = None,
) -> Optional[Chat]:
    query = db.query(Chat).filter(Chat.id == chat_id)
    if user_id is not None:
        query = query.filter(Chat.user_id == user_id)
    return query.first()


def list_for_user(
    db: Session,
    user_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
) -> list[Chat]:
    query = db.query(Chat).filter(Chat.user_id == user_id)
    if status:
        query = query.filter(Chat.status == ChatStatus(status))
    if specialty:
        query = query.filter(Chat.specialty == specialty)
    return query.order_by(Chat.created_at.desc()).offset(skip).limit(limit).all()


def create(
    db: Session,
    *,
    user_id: int,
    title: str = "New Chat",
    specialty: Optional[str] = None,
    severity: Optional[str] = None,
) -> Chat:
    chat = Chat(
        title=title,
        specialty=specialty,
        severity=severity,
        user_id=user_id,
        status=ChatStatus.OPEN,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def update(db: Session, chat: Chat, **fields) -> Chat:
    for key, value in fields.items():
        setattr(chat, key, value)
    db.commit()
    db.refresh(chat)
    return chat


def delete(db: Session, chat: Chat) -> None:
    db.delete(chat)
    db.commit()

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

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


async def async_get(
    db: AsyncSession,
    chat_id: int,
    user_id: Optional[int] = None,
) -> Optional[Chat]:
    stmt = select(Chat).options(selectinload(Chat.files)).where(Chat.id == chat_id)
    if user_id is not None:
        stmt = stmt.where(Chat.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def list_for_user(
    db: Session,
    user_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    include_archived: bool = False,
) -> list[Chat]:
    query = db.query(Chat).filter(Chat.user_id == user_id)
    if not include_archived:
        query = query.filter(Chat.is_archived == False)
    if status:
        query = query.filter(Chat.status == ChatStatus(status))
    if specialty:
        query = query.filter(Chat.specialty == specialty)
    if search:
        query = query.filter(Chat.title.ilike(f"%{search}%"))
    if date_from:
        query = query.filter(Chat.created_at >= date_from)
    if date_to:
        query = query.filter(Chat.created_at <= date_to)
    return query.order_by(Chat.created_at.desc()).offset(skip).limit(limit).all()


def create(
    db: Session,
    *,
    user_id: int,
    title: str = "New Chat",
    specialty: Optional[str] = None,
    severity: Optional[str] = None,
    patient_context: Optional[dict] = None,
) -> Chat:
    chat = Chat(
        title=title,
        specialty=specialty,
        severity=severity,
        patient_context=patient_context,
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


async def async_update(db: AsyncSession, chat: Chat, **fields) -> Chat:
    for key, value in fields.items():
        setattr(chat, key, value)
    await db.commit()
    await db.refresh(chat)
    return chat


def archive(db: Session, chat: Chat) -> None:
    chat.is_archived = True
    db.commit()
    db.refresh(chat)


def delete(db: Session, chat: Chat) -> None:
    db.delete(chat)
    db.commit()

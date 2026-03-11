from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.db.models import Message


def create(
    db: Session,
    *,
    chat_id: int,
    content: str,
    sender: str,
    citations: Optional[list] = None,
    is_generating: bool = False,
) -> Message:
    msg = Message(
        chat_id=chat_id,
        content=content,
        role=sender,
        sender=sender,
        citations=citations,
        is_generating=is_generating,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


async def async_create(
    db: AsyncSession,
    *,
    chat_id: int,
    content: str,
    sender: str,
    citations: Optional[list] = None,
    is_generating: bool = False,
) -> Message:
    msg = Message(chat_id=chat_id, content=content, sender=sender, citations=citations, is_generating=is_generating)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


def list_for_chat(db: Session, chat_id: int) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )


async def async_update(db: AsyncSession, msg: Message, **fields) -> Message:
    for key, value in fields.items():
        setattr(msg, key, value)
    await db.commit()
    await db.refresh(msg)
    return msg

from typing import Optional
from sqlalchemy.orm import Session

from src.db.models import Message


def create(
    db: Session,
    *,
    chat_id: int,
    content: str,
    sender: str,
    citations: Optional[list] = None,
) -> Message:
    msg = Message(chat_id=chat_id, content=content, sender=sender, citations=citations)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def list_for_chat(db: Session, chat_id: int) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )

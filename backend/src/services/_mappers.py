"""
Shared ORM → schema conversion helpers.
Centralises the two helpers that were previously duplicated
in api/chats.py and api/specialist.py.
"""

from src.db.models import Chat, Message
from src.schemas.chat import ChatResponse, MessageResponse


def chat_to_response(chat: Chat) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status.value,
        specialty=chat.specialty,
        severity=chat.severity,
        specialist_id=chat.specialist_id,
        assigned_at=chat.assigned_at,
        reviewed_at=chat.reviewed_at,
        review_feedback=chat.review_feedback,
        created_at=chat.created_at.isoformat() if chat.created_at else "",
        user_id=chat.user_id,
    )


def msg_to_response(m: Message) -> MessageResponse:
    return MessageResponse(
        id=m.id,
        content=m.content,
        sender=m.sender,
        created_at=m.created_at.isoformat() if m.created_at else "",
        citations=m.citations,
    )

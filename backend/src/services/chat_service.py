from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.db.models import Chat, ChatStatus, User
from src.repositories import audit_repository, chat_repository, message_repository
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
    MessageResponse,
)
from src.services._mappers import chat_to_response, msg_to_response


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_chat(db: Session, user: User, data: ChatCreate) -> ChatResponse:
    chat = chat_repository.create(
        db,
        user_id=user.id,
        title=data.title,
        specialty=data.specialty,
        severity=data.severity,
    )
    audit_repository.log(
        db, user_id=user.id, action="CREATE_CHAT", details=f"Created chat: {data.title}"
    )
    return chat_to_response(chat)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

def list_chats(
    db: Session,
    user: User,
    *,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
) -> list[ChatResponse]:
    if status:
        try:
            ChatStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    chats = chat_repository.list_for_user(
        db, user.id, skip=skip, limit=limit, status=status, specialty=specialty
    )
    return [chat_to_response(c) for c in chats]


# ---------------------------------------------------------------------------
# Get (with messages)
# ---------------------------------------------------------------------------

def get_chat(db: Session, user: User, chat_id: int) -> ChatWithMessages:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    audit_repository.log(
        db, user_id=user.id, action="VIEW_CHAT", details=f"Viewed chat {chat_id}"
    )
    messages = message_repository.list_for_chat(db, chat.id)
    response = ChatWithMessages(**chat_to_response(chat).model_dump())
    response.messages = [msg_to_response(m) for m in messages]
    return response

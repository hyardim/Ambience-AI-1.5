import os
from typing import Optional

import httpx
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


RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001")


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


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_chat(
    db: Session, user: User, chat_id: int, payload: ChatUpdate
) -> ChatResponse:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Block metadata edits after specialist assignment
    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit chat details after specialist assignment (current: {chat.status.value})",
        )

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
    audit_repository.log(
        db, user_id=user.id, action="UPDATE_CHAT", details=f"Updated chat {chat_id}"
    )
    return chat_to_response(chat)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_chat(db: Session, user: User, chat_id: int) -> None:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat_repository.delete(db, chat)
    audit_repository.log(
        db, user_id=user.id, action="DELETE_CHAT", details=f"Deleted chat {chat_id}"
    )


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------

def send_message(db: Session, user: User, chat_id: int, content: str) -> dict:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # GP can only send messages before a specialist picks up the chat
    if chat.status not in (ChatStatus.OPEN, ChatStatus.SUBMITTED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send messages in {chat.status.value} state",
        )

    message_repository.create(db, chat_id=chat.id, content=content, sender="user")
    rag_payload = {"query": content, "top_k": 4}

    try:
        rag_response = httpx.post(
            f"{RAG_SERVICE_URL}/answer", json=rag_payload, timeout=60
        )
        rag_response.raise_for_status()
        rag_json = rag_response.json()
        ai_content = rag_json.get("answer", "")
        citations = rag_json.get("citations", [])
    except Exception as exc:  # pragma: no cover - network fallback
        ai_content = (
            "RAG service unavailable right now. Please try again later. "
            f"(detail: {exc})"
        )
        citations = None

    ai_msg = message_repository.create(
        db,
        chat_id=chat.id,
        content=ai_content,
        sender="ai",
        citations=citations,
    )

    if chat.status == ChatStatus.OPEN:
        chat_repository.update(db, chat, status=ChatStatus.SUBMITTED)
        audit_repository.log(
            db,
            user_id=user.id,
            action="AUTO_SUBMIT_FOR_REVIEW",
            details=f"Chat {chat_id} auto-submitted after AI response",
        )

    return {"status": "Message sent", "ai_response": ai_msg.content}


# ---------------------------------------------------------------------------
# Submit for review
# ---------------------------------------------------------------------------

def submit_for_review(db: Session, user: User, chat_id: int) -> ChatResponse:
    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.OPEN:
        raise HTTPException(
            status_code=400,
            detail=f"Only OPEN chats can be submitted (current: {chat.status.value})",
        )

    chat = chat_repository.update(db, chat, status=ChatStatus.SUBMITTED)
    audit_repository.log(
        db,
        user_id=user.id,
        action="SUBMIT_FOR_REVIEW",
        details=f"Chat {chat_id} submitted for specialist review",
    )
    return chat_to_response(chat)

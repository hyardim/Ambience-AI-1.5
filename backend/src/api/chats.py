<<<<<<< HEAD
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
=======
from typing import List, Optional
>>>>>>> main

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.db.models import User
from src.db.session import get_db
from src.schemas.chat import (
    ChatCreate, ChatResponse, ChatUpdate, ChatWithMessages, MessageCreate,
)
from src.services import chat_service

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag_service:8001")

router = APIRouter()


@router.post("/", response_model=ChatResponse)
def create_chat(
    chat_data: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
<<<<<<< HEAD
    """Creates a new conversation for the current user."""
    user = _get_user_by_email_or_404(db, current_user["email"])

    new_chat = Chat(
        user_id=user.id,
        title=chat_data.title or "New Consultation",
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)

    return new_chat
=======
    return chat_service.create_chat(db, current_user, chat_data)
>>>>>>> main


@router.get("/", response_model=List[ChatResponse])
def list_chats(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
<<<<<<< HEAD
    """Returns a list of all conversations for the current user."""
    user = _get_user_by_email_or_404(db, current_user["email"])

    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return chats
=======
    return chat_service.list_chats(db, current_user, skip=skip, limit=limit, status=status, specialty=specialty)
>>>>>>> main


@router.get("/{chat_id}", response_model=ChatWithMessages)
def get_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
<<<<<<< HEAD
    """Returns a single conversation for the current user."""
    user = _get_user_by_email_or_404(db, current_user["email"])
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat
=======
    return chat_service.get_chat(db, current_user, chat_id)


@router.patch("/{chat_id}", response_model=ChatResponse)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.update_chat(db, current_user, chat_id, payload)
>>>>>>> main


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
<<<<<<< HEAD
    """Deletes a specific conversation."""
    user = _get_user_by_email_or_404(db, current_user["email"])

    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    db.delete(chat)
    db.commit()
    return None
=======
    chat_service.delete_chat(db, current_user, chat_id)
>>>>>>> main


@router.post("/{chat_id}/message")
def send_message(
    chat_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
<<<<<<< HEAD
    """Saves user message and returns an assistant response via RAG service."""
    user = _get_user_by_email_or_404(db, current_user["email"])
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_msg = Message(chat_id=chat.id, role="user", content=message.content)
    db.add(user_msg)
    db.commit()

    rag_payload = {"query": message.content, "top_k": 4}
    try:
        rag_response = httpx.post(
            f"{RAG_SERVICE_URL}/answer", json=rag_payload, timeout=60
        )
        rag_response.raise_for_status()
        rag_json = rag_response.json()
        answer_text = rag_json.get("answer", "")

        citations = rag_json.get("citations", [])
        if citations:
            source_lines = []
            for idx, c in enumerate(citations, start=1):
                source = c.get("source", "Unknown Source")
                page_start = c.get("page_start")
                page_end = c.get("page_end")
                if page_start is not None and page_end is not None:
                    if page_start == page_end:
                        page_note = f" (page {page_start})"
                    else:
                        page_note = f" (pages {page_start}-{page_end})"
                else:
                    page_note = ""
                source_lines.append(f"[{idx}] {source}{page_note}")
            answer_text = answer_text + "\n\nSources:\n" + "\n".join(source_lines)
    except Exception as exc:
        answer_text = (
            "RAG service unavailable right now. Please try again later. "
            f"(detail: {exc})"
        )

    ai_msg = Message(chat_id=chat.id, role="assistant", content=answer_text)
    db.add(ai_msg)
    db.commit()
    db.refresh(ai_msg)

    return ai_msg
    return ai_msg
=======
    return chat_service.send_message(db, current_user, chat_id, message.content)


@router.post("/{chat_id}/submit", response_model=ChatResponse)
def submit_for_review(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.submit_for_review(db, current_user, chat_id)
>>>>>>> main

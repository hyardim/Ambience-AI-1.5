from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.db.session import get_db
from src.db.models import Chat, Message, User, ChatStatus, AuditLog
from src.core import security
from src.schemas.chat import (
    ChatCreate, ChatUpdate, ChatResponse, ChatWithMessages,
    MessageCreate, MessageResponse,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_current_user_obj(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chat_to_response(chat: Chat) -> ChatResponse:
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


def _msg_to_response(m: Message) -> MessageResponse:
    return MessageResponse(
        id=m.id,
        content=m.content,
        sender=m.sender,
        created_at=m.created_at.isoformat() if m.created_at else "",
        citations=m.citations,
    )


# ---------------------------------------------------------------------------
# POST /chats/  — create
# ---------------------------------------------------------------------------

@router.post("/", response_model=ChatResponse)
def create_chat(
    chat_data: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    new_chat = Chat(
        title=chat_data.title,
        specialty=chat_data.specialty,
        severity=chat_data.severity,
        user_id=current_user.id,
        status=ChatStatus.OPEN,
    )
    db.add(new_chat)
    db.add(AuditLog(
        user_id=current_user.id,
        action="CREATE_CHAT",
        details=f"Created chat: {chat_data.title}",
    ))
    db.commit()
    db.refresh(new_chat)
    return _chat_to_response(new_chat)


# ---------------------------------------------------------------------------
# GET /chats/  — list
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[ChatResponse])
def list_chats(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    specialty: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    """List the current user's chats with optional status/specialty filtering."""
    query = db.query(Chat).filter(Chat.user_id == current_user.id)

    if status:
        try:
            query = query.filter(Chat.status == ChatStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if specialty:
        query = query.filter(Chat.specialty == specialty)

    chats = query.order_by(Chat.created_at.desc()).offset(skip).limit(limit).all()
    return [_chat_to_response(c) for c in chats]


# ---------------------------------------------------------------------------
# GET /chats/{chat_id}  — detail with messages
# ---------------------------------------------------------------------------

@router.get("/{chat_id}", response_model=ChatWithMessages)
def get_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id,
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    db.add(AuditLog(
        user_id=current_user.id,
        action="VIEW_CHAT",
        details=f"Viewed chat {chat_id}",
    ))
    db.commit()

    messages = db.query(Message).filter(Message.chat_id == chat.id).all()
    response = ChatWithMessages(**_chat_to_response(chat).model_dump())
    response.messages = [_msg_to_response(m) for m in messages]
    return response


# ---------------------------------------------------------------------------
# PATCH /chats/{chat_id}  — update title / status / specialty / severity
# ---------------------------------------------------------------------------

@router.patch("/{chat_id}", response_model=ChatResponse)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    """Update mutable chat fields. Only the owning GP can call this."""
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id,
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if payload.title is not None:
        chat.title = payload.title
    if payload.specialty is not None:
        chat.specialty = payload.specialty
    if payload.severity is not None:
        chat.severity = payload.severity
    if payload.status is not None:
        try:
            chat.status = ChatStatus(payload.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {payload.status}")

    db.add(AuditLog(
        user_id=current_user.id,
        action="UPDATE_CHAT",
        details=f"Updated chat {chat_id}",
    ))
    db.commit()
    db.refresh(chat)
    return _chat_to_response(chat)


# ---------------------------------------------------------------------------
# DELETE /chats/{chat_id}
# ---------------------------------------------------------------------------

@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id,
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    db.delete(chat)
    db.add(AuditLog(
        user_id=current_user.id,
        action="DELETE_CHAT",
        details=f"Deleted chat {chat_id}",
    ))
    db.commit()


# ---------------------------------------------------------------------------
# POST /chats/{chat_id}/message
# ---------------------------------------------------------------------------

@router.post("/{chat_id}/message")
def send_message(
    chat_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id,
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    user_msg = Message(content=message.content, sender="user", chat_id=chat.id)
    db.add(user_msg)

    ai_msg = Message(
        content=f"I received: {message.content}",
        sender="ai",
        chat_id=chat.id,
        citations=[],
    )
    db.add(ai_msg)
    db.commit()

    return {"status": "Message sent", "ai_response": ai_msg.content}


# ---------------------------------------------------------------------------
# POST /chats/{chat_id}/submit  — GP submits for specialist review
# ---------------------------------------------------------------------------

@router.post("/{chat_id}/submit", response_model=ChatResponse)
def submit_for_review(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    """Move a chat from OPEN → SUBMITTED so it appears in the specialist queue."""
    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.user_id == current_user.id,
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.OPEN:
        raise HTTPException(
            status_code=400,
            detail=f"Only OPEN chats can be submitted (current: {chat.status.value})",
        )

    chat.status = ChatStatus.SUBMITTED
    db.add(AuditLog(
        user_id=current_user.id,
        action="SUBMIT_FOR_REVIEW",
        details=f"Chat {chat_id} submitted for specialist review",
    ))
    db.commit()
    db.refresh(chat)
    return _chat_to_response(chat)

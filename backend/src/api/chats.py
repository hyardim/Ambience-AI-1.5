from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.core import security
from src.db.models import User
from src.db.session import get_async_db, get_db
from src.repositories import user_repository
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
    MessageCreate,
)
from src.services import chat_service
from src.utils.sse import sse_event_generator

router = APIRouter()


@router.post("/", response_model=ChatResponse)
def create_chat(
    chat_data: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.create_chat(db, current_user, chat_data)


@router.get("/", response_model=List[ChatResponse])
def list_chats(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    search: Optional[str] = Query(None, max_length=200),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.list_chats(
        db,
        current_user,
        skip=skip,
        limit=limit,
        status=status,
        specialty=specialty,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/{chat_id}", response_model=ChatWithMessages)
def get_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.get_chat(db, current_user, chat_id)


@router.patch("/{chat_id}", response_model=ChatResponse)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.update_chat(db, current_user, chat_id, payload)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    chat_service.archive_chat(db, current_user, chat_id)


@router.post("/{chat_id}/message")
async def send_message(
    chat_id: int,
    message: MessageCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_obj),
):
    return await chat_service.async_send_message(
        db,
        current_user,
        chat_id,
        message.content,
    )


@router.post("/{chat_id}/submit", response_model=ChatResponse)
def submit_for_review(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.submit_for_review(db, current_user, chat_id)


@router.get("/{chat_id}/stream")
async def stream_chat(
    chat_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """SSE endpoint for real-time AI generation events.

    EventSource does not support custom headers, so the JWT is passed as a
    query parameter.  The token is validated before the stream begins.
    """
    # Validate token and resolve user
    try:
        email = security.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = user_repository.get_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Verify the user owns this chat or has the same specialist access as the
    # specialist chat-detail view (assigned chat, or submitted queue chat in
    # their specialty).
    from src.repositories import chat_repository
    from src.db.models import Chat, ChatStatus, UserRole

    chat = chat_repository.get(db, chat_id, user_id=user.id)
    if not chat:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat and user.role == UserRole.SPECIALIST:
            in_queue = chat.status == ChatStatus.SUBMITTED and (
                not user.specialty or chat.specialty == user.specialty
            )
            assigned_to_me = chat.specialist_id == user.id
            if not (in_queue or assigned_to_me):
                chat = None
        else:
            chat = None
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return StreamingResponse(
        sse_event_generator(chat_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

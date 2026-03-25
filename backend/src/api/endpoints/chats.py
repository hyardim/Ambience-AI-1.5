from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.db.models import User
from src.db.session import get_async_db, get_db
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
    FileAttachmentResponse,
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
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
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


@router.post(
    "/{chat_id}/files",
    response_model=FileAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    chat_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return await chat_service.upload_file(db, current_user, chat_id, file)


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
    current_user: User = Depends(get_current_user_obj),
    db: Session = Depends(get_db),
):
    """SSE endpoint for real-time AI generation events.

    Uses the same auth dependency chain as other protected routes so
    session_version invalidation and token validation are consistent.
    """
    from src.core.chat_policy import can_stream_chat
    from src.db.models import Chat

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat or not can_stream_chat(current_user, chat):
        raise HTTPException(status_code=404, detail="Chat not found")

    return StreamingResponse(
        sse_event_generator(chat_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

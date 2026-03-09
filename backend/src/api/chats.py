from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.db.models import User
from src.db.session import get_db
from src.schemas.chat import (
    ChatCreate,
    ChatResponse,
    ChatUpdate,
    ChatWithMessages,
    MessageCreate,
)
from src.services import chat_service

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
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    chat_service.delete_chat(db, current_user, chat_id)


@router.post("/{chat_id}/message")
def send_message(
    chat_id: int,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.send_message(
        db,
        current_user,
        chat_id,
        message.content,
        background_tasks,
    )


@router.post("/{chat_id}/submit", response_model=ChatResponse)
def submit_for_review(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return chat_service.submit_for_review(db, current_user, chat_id)

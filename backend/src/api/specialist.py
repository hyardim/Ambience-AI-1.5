from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_specialist_user
from src.db.models import User
from src.db.session import get_db
from src.schemas.chat import AssignRequest, ChatResponse, ChatWithMessages, MessageCreate, ReviewRequest
from src.services import specialist_service

router = APIRouter()


@router.get("/queue", response_model=List[ChatResponse])
def get_queue(
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.get_queue(db, specialist)


@router.get("/assigned", response_model=List[ChatResponse])
def get_assigned(
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.get_assigned(db, specialist)


@router.get("/chats/{chat_id}", response_model=ChatWithMessages)
def get_chat_detail(
    chat_id: int,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.get_chat_detail(db, specialist, chat_id)


@router.post("/chats/{chat_id}/assign", response_model=ChatResponse)
def assign_specialist(
    chat_id: int,
    body: AssignRequest,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.assign(db, specialist, chat_id, body)


@router.post("/chats/{chat_id}/review", response_model=ChatResponse)
def review_chat(
    chat_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.review(db, specialist, chat_id, body)


@router.post("/chats/{chat_id}/messages/{message_id}/review", response_model=ChatResponse)
def review_message(
    chat_id: int,
    message_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.review_message(db, specialist, chat_id, message_id, body)


@router.post("/chats/{chat_id}/message")
def send_message(
    chat_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    return specialist_service.send_message(db, specialist, chat_id, message.content)

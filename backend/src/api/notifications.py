from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.db.models import User
from src.db.session import get_db
from src.schemas.notification import NotificationResponse
from src.services import notification_service

router = APIRouter()


@router.get("/", response_model=List[NotificationResponse])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return notification_service.list_notifications(db, current_user, unread_only=unread_only)


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return notification_service.mark_read(db, current_user, notification_id)


@router.patch("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return notification_service.mark_all_read(db, current_user)

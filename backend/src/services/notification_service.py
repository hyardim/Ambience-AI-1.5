from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.db.models import User
from src.repositories import notification_repository
from src.schemas.notification import NotificationResponse


def _to_response(n) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        type=n.type.value,
        title=n.title,
        body=n.body,
        chat_id=n.chat_id,
        is_read=n.is_read,
        created_at=n.created_at,
    )


def list_notifications(
    db: Session, user: User, *, unread_only: bool = False
) -> list[NotificationResponse]:
    notifs = notification_repository.list_for_user(db, user.id, unread_only=unread_only)
    return [_to_response(n) for n in notifs]


def mark_read(db: Session, user: User, notification_id: int) -> NotificationResponse:
    notif = notification_repository.mark_read(db, notification_id, user.id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    return _to_response(notif)


def mark_all_read(db: Session, user: User) -> dict:
    count = notification_repository.mark_all_read(db, user.id)
    return {"marked_read": count}

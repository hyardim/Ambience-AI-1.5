from typing import Optional
from sqlalchemy.orm import Session

from src.db.models import Notification, NotificationType


def create(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    title: str,
    body: Optional[str] = None,
    chat_id: Optional[int] = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        chat_id=chat_id,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def list_for_user(
    db: Session, user_id: int, *, unread_only: bool = False
) -> list[Notification]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    return query.order_by(Notification.created_at.desc()).all()


def mark_read(
    db: Session, notification_id: int, user_id: int
) -> Optional[Notification]:
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id,
    ).first()
    if not notif:
        return None
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return notif


def mark_all_read(db: Session, user_id: int) -> int:
    count = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .update({"is_read": True})
    )
    db.commit()
    return count

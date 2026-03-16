from src.core.config import settings
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.db.models import User
from src.repositories import notification_repository
from src.schemas.notification import NotificationResponse
from src.utils.cache import cache, cache_keys


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


def invalidate_notification_caches(user_id: int) -> None:
    cache.delete_pattern_sync(
        cache_keys.notifications_pattern(user_id),
        user_id=user_id,
        resource="notifications",
    )
    cache.delete_sync(
        cache_keys.notifications_unread_count(user_id),
        user_id=user_id,
        resource="notifications",
    )


def list_notifications(
    db: Session, user: User, *, unread_only: bool = False
) -> list[NotificationResponse]:
    cache_key = cache_keys.notifications(user.id, unread_only=unread_only)
    cached = cache.get_sync(cache_key, user_id=user.id, resource="notifications")
    if cached is not None:
        return [NotificationResponse(**item) for item in cached]

    notifs = notification_repository.list_for_user(db, user.id, unread_only=unread_only)
    response = [_to_response(n) for n in notifs]
    cache.set_sync(
        cache_key,
        [item.model_dump() for item in response],
        ttl=settings.CACHE_NOTIFICATION_TTL,
        user_id=user.id,
        resource="notifications",
    )
    return response


def mark_read(db: Session, user: User, notification_id: int) -> NotificationResponse:
    notif = notification_repository.mark_read(db, notification_id, user.id)
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    invalidate_notification_caches(user.id)
    return _to_response(notif)


def mark_all_read(db: Session, user: User) -> dict:
    count = notification_repository.mark_all_read(db, user.id)
    invalidate_notification_caches(user.id)
    return {"marked_read": count}


def get_unread_count(db: Session, user: User) -> dict:
    cache_key = cache_keys.notifications_unread_count(user.id)
    cached = cache.get_sync(cache_key, user_id=user.id, resource="notifications")
    if cached is not None:
        return {"unread_count": int(cached["unread_count"])}

    unread_count = notification_repository.count_unread(db, user.id)
    payload = {"unread_count": unread_count}
    cache.set_sync(
        cache_key,
        payload,
        ttl=settings.CACHE_NOTIFICATION_TTL,
        user_id=user.id,
        resource="notifications",
    )
    return payload

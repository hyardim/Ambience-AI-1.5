from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.core.chat_policy import can_view_chat
from src.core.config import settings
from src.db.models import Chat, ChatStatus, NotificationType, User
from src.repositories import (
    audit_repository,
    chat_repository,
    message_repository,
    notification_repository,
)
from src.schemas.chat import AssignRequest, ChatResponse, ChatWithMessages
from src.services._mappers import chat_to_response, msg_to_response
from src.services.cache_invalidation import (
    invalidate_admin_chat_caches_sync,
    invalidate_admin_stats_sync,
    invalidate_specialist_lists_sync,
)
from src.services.notification_service import invalidate_notification_caches
from src.utils.cache import cache, cache_keys


def get_queue(db: Session, specialist: User) -> list[ChatResponse]:
    cache_key = cache_keys.specialist_queue(specialist.specialty)
    cached = cache.get_sync(
        cache_key, user_id=specialist.id, resource="specialist_queue"
    )
    if cached is not None:
        return [ChatResponse(**item) for item in cached]

    query = db.query(Chat).filter(Chat.status == ChatStatus.SUBMITTED)
    if specialist.specialty:
        query = query.filter(Chat.specialty == specialist.specialty)
    chats = query.order_by(Chat.created_at.asc()).all()
    response = [chat_to_response(c) for c in chats]
    cache.set_sync(
        cache_key,
        [item.model_dump() for item in response],
        ttl=settings.CACHE_SPECIALIST_LIST_TTL,
        user_id=specialist.id,
        resource="specialist_queue",
    )
    return response


def get_assigned(db: Session, specialist: User) -> list[ChatResponse]:
    cache_key = cache_keys.specialist_assigned(specialist.id)
    cached = cache.get_sync(
        cache_key, user_id=specialist.id, resource="specialist_assigned"
    )
    if cached is not None:
        return [ChatResponse(**item) for item in cached]

    chats = (
        db.query(Chat)
        .filter(
            Chat.specialist_id == specialist.id,
            Chat.status.in_([ChatStatus.ASSIGNED, ChatStatus.REVIEWING]),
        )
        .order_by(Chat.assigned_at.asc())
        .all()
    )
    response = [chat_to_response(c) for c in chats]
    cache.set_sync(
        cache_key,
        [item.model_dump() for item in response],
        ttl=settings.CACHE_SPECIALIST_LIST_TTL,
        user_id=specialist.id,
        resource="specialist_assigned",
    )
    return response


def get_chat_detail(db: Session, specialist: User, chat_id: int) -> ChatWithMessages:
    cache_key = cache_keys.chat_detail(specialist.id, chat_id)
    cached = cache.get_sync(cache_key, user_id=specialist.id, resource="chat_detail")
    if cached is not None:
        return ChatWithMessages(**cached)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if not can_view_chat(specialist, chat):
        raise HTTPException(
            status_code=403, detail="You do not have access to this chat"
        )

    messages = message_repository.list_for_chat(db, chat.id)
    response = ChatWithMessages(**chat_to_response(chat).model_dump())
    response.messages = [msg_to_response(m) for m in messages]
    cache.set_sync(
        cache_key,
        response.model_dump(),
        ttl=settings.CACHE_CHAT_DETAIL_TTL,
        user_id=specialist.id,
        resource="chat_detail",
    )
    return response


def assign(
    db: Session, specialist: User, chat_id: int, body: AssignRequest
) -> ChatResponse:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"Chat is not in SUBMITTED state (current: {chat.status.value})",
        )
    if body.specialist_id != specialist.id:
        raise HTTPException(
            status_code=403, detail="You can only assign yourself to a chat"
        )

    if (
        specialist.specialty
        and chat.specialty
        and specialist.specialty != chat.specialty
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Your specialty ({specialist.specialty}) does not match this chat's specialty ({chat.specialty})",
        )

    chat = chat_repository.update(
        db,
        chat,
        specialist_id=specialist.id,
        status=ChatStatus.ASSIGNED,
        assigned_at=datetime.now(timezone.utc),
    )
    audit_repository.log(
        db,
        user_id=specialist.id,
        action="ASSIGN_SPECIALIST",
        details=f"Specialist #{specialist.id} assigned to chat {chat_id}",
    )
    notification_repository.create(
        db,
        user_id=chat.user_id,
        type=NotificationType.CHAT_ASSIGNED,
        title="Chat assigned to a specialist",
        body=f"Your chat '{chat.title}' has been picked up by {specialist.full_name or specialist.email}.",
        chat_id=chat.id,
    )
    invalidate_notification_caches(chat.user_id)
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id),
        user_id=specialist.id,
        resource="chat_detail",
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(chat.user_id),
        user_id=chat.user_id,
        resource="chat_list",
    )
    invalidate_specialist_lists_sync(
        specialty=chat.specialty,
        specialist_id=specialist.id,
    )
    invalidate_admin_chat_caches_sync(chat.id)
    invalidate_admin_stats_sync()
    return chat_to_response(chat)

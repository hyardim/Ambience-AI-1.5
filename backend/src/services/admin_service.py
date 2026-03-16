from typing import Optional
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import AuditLog, Chat, ChatStatus, Message, User, UserRole
from src.repositories import chat_repository, message_repository, user_repository
from src.schemas.auth import UserOut
from src.schemas.chat import ChatUpdate, ChatWithMessages
from src.services._mappers import chat_to_response, msg_to_response
from src.utils.cache import cache, cache_keys


def _invalidate_admin_stats_cache() -> None:
    cache.delete_sync(cache_keys.admin_stats(), resource="admin_stats")


def _invalidate_admin_chat_caches(chat_id: Optional[int] = None) -> None:
    cache.delete_pattern_sync(
        cache_keys.admin_chat_list_pattern(), resource="admin_chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.admin_chat_detail_pattern(chat_id), resource="admin_chat_detail"
    )


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

def get_stats(db: Session) -> dict:
    cache_key = cache_keys.admin_stats()
    cached = cache.get_sync(cache_key, resource="admin_stats")
    if cached is not None:
        return cached

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    total_ai = db.query(func.count(Message.id)).filter(
        Message.sender == "ai").scalar() or 0
    rag_grounded = db.query(func.count(Message.id)).filter(
        Message.sender == "ai", Message.citations.isnot(None)
    ).scalar() or 0
    specialist_responses = db.query(func.count(Message.id)).filter(
        Message.sender == "specialist").scalar() or 0

    active_statuses = [ChatStatus.OPEN, ChatStatus.SUBMITTED,
                       ChatStatus.ASSIGNED, ChatStatus.REVIEWING]
    active_consultations = db.query(func.count(Chat.id)).filter(
        Chat.status.in_(active_statuses)).scalar() or 0

    chats_by_status = {
        row[0].value: row[1]
        for row in db.query(Chat.status, func.count(Chat.id)).group_by(Chat.status).all()
    }
    chats_by_specialty = {
        (row[0] or "unknown"): row[1]
        for row in db.query(Chat.specialty, func.count(Chat.id)).group_by(Chat.specialty).all()
    }
    active_users_by_role = {
        row[0].value: row[1]
        for row in db.query(User.role, func.count(User.id))
        .filter(User.is_active)
        .group_by(User.role).all()
    }

    daily_rows = (
        db.query(func.date(Message.created_at).label(
            "day"), func.count(Message.id))
        .filter(Message.sender == "ai", Message.created_at >= thirty_days_ago)
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_ai_queries = [
        {"date": str(row[0])[:10], "count": row[1]} for row in daily_rows]

    stats = {
        "total_ai_responses": total_ai,
        "rag_grounded_responses": rag_grounded,
        "specialist_responses": specialist_responses,
        "active_consultations": active_consultations,
        "chats_by_status": chats_by_status,
        "chats_by_specialty": chats_by_specialty,
        "active_users_by_role": active_users_by_role,
        "daily_ai_queries": daily_ai_queries,
    }
    cache.set_sync(
        cache_key,
        stats,
        ttl=settings.CACHE_ADMIN_STATS_TTL,
        resource="admin_stats",
    )
    return stats


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

class UserUpdateAdmin:
    def __init__(
        self,
        full_name: Optional[str] = None,
        specialty: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ):
        self.full_name = full_name
        self.specialty = specialty
        self.role = role
        self.is_active = is_active


def list_users(db: Session, role: Optional[str] = None) -> list[UserOut]:
    query = db.query(User)
    if role:
        try:
            query = query.filter(User.role == UserRole(role))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid role: {role}")
    users = query.order_by(User.id).all()
    return [UserOut.model_validate(u) for u in users]


def get_user(db: Session, user_id: int) -> UserOut:
    cache_key = cache_keys.user_profile(user_id)
    cached = cache.get_sync(cache_key, user_id=user_id,
                            resource="user_profile")
    if cached is not None:
        return UserOut(**cached)

    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    response = UserOut.model_validate(user)
    cache.set_sync(
        cache_key,
        response.model_dump(),
        ttl=settings.CACHE_PROFILE_TTL,
        user_id=user_id,
        resource="user_profile",
    )
    return response


def update_user(db: Session, user_id: int, payload: UserUpdateAdmin) -> UserOut:
    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    fields: dict = {}
    if payload.full_name is not None:
        fields["full_name"] = payload.full_name
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty
    if payload.is_active is not None:
        fields["is_active"] = payload.is_active
    if payload.role is not None:
        try:
            fields["role"] = UserRole(payload.role)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid role: {payload.role}")

    user = user_repository.update(db, user, **fields)
    cache.delete_sync(cache_keys.user_profile(user_id),
                      user_id=user_id, resource="user_profile")
    _invalidate_admin_stats_cache()
    return UserOut.model_validate(user)


def deactivate_user(db: Session, user_id: int) -> UserOut:
    user = user_repository.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user = user_repository.update(db, user, is_active=False)
    cache.delete_sync(cache_keys.user_profile(user_id),
                      user_id=user_id, resource="user_profile")
    _invalidate_admin_stats_cache()
    return UserOut.model_validate(user)


# ---------------------------------------------------------------------------
# Chat management
# ---------------------------------------------------------------------------

def list_all_chats(
    db: Session,
    status: Optional[str] = None,
    specialty: Optional[str] = None,
    user_id: Optional[int] = None,
    specialist_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> list[dict]:
    cache_key = cache_keys.admin_chat_list(
        status=status,
        specialty=specialty,
        user_id=user_id,
        specialist_id=specialist_id,
        skip=skip,
        limit=limit,
    )
    cached = cache.get_sync(cache_key, resource="admin_chat_list")
    if cached is not None:
        return cached

    query = db.query(Chat)
    if status:
        try:
            query = query.filter(Chat.status == ChatStatus(status))
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {status}")
    if specialty:
        query = query.filter(Chat.specialty == specialty)
    if user_id:
        query = query.filter(Chat.user_id == user_id)
    if specialist_id:
        query = query.filter(Chat.specialist_id == specialist_id)

    chats = query.order_by(Chat.created_at.desc()).offset(
        skip).limit(limit).all()

    result = []
    for c in chats:
        entry = chat_to_response(c).model_dump()
        entry["owner_identifier"] = f"{c.owner.role.value}_{c.owner.id}" if c.owner else None
        entry["specialist_identifier"] = f"{c.specialist.role.value}_{c.specialist.id}" if c.specialist else None
        result.append(entry)
    cache.set_sync(
        cache_key,
        result,
        ttl=settings.CACHE_ADMIN_CHAT_TTL,
        resource="admin_chat_list",
    )
    return result


def get_any_chat(db: Session, chat_id: int) -> ChatWithMessages:
    cache_key = cache_keys.admin_chat_detail(chat_id)
    cached = cache.get_sync(cache_key, resource="admin_chat_detail")
    if cached is not None:
        return ChatWithMessages(**cached)

    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = message_repository.list_for_chat(db, chat.id)
    resp = ChatWithMessages(**chat_to_response(chat).model_dump())
    resp.messages = [msg_to_response(m) for m in messages]
    cache.set_sync(
        cache_key,
        resp.model_dump(),
        ttl=settings.CACHE_ADMIN_CHAT_TTL,
        resource="admin_chat_detail",
    )
    return resp


def update_any_chat(db: Session, chat_id: int, payload: ChatUpdate) -> dict:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    fields: dict = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty
    if payload.severity is not None:
        fields["severity"] = payload.severity
    if payload.status is not None:
        try:
            fields["status"] = ChatStatus(payload.status)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {payload.status}")

    chat = chat_repository.update(db, chat, **fields)
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), resource="chat_detail"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(chat.user_id), user_id=chat.user_id, resource="chat_list"
    )
    _invalidate_admin_chat_caches(chat_id)
    _invalidate_admin_stats_cache()
    entry = chat_to_response(chat).model_dump()
    entry["owner_identifier"] = f"{chat.owner.role.value}_{chat.owner.id}" if chat.owner else None
    entry["specialist_identifier"] = f"{chat.specialist.role.value}_{chat.specialist.id}" if chat.specialist else None
    return entry


def delete_any_chat(db: Session, chat_id: int) -> None:
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat_repository.delete(db, chat)
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), resource="chat_detail"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(chat.user_id), user_id=chat.user_id, resource="chat_list"
    )
    _invalidate_admin_chat_caches(chat_id)
    _invalidate_admin_stats_cache()


# ---------------------------------------------------------------------------
# Audit log viewing
# ---------------------------------------------------------------------------

_ACTION_CATEGORIES: dict[str, set[str]] = {
    "AUTH":       {"LOGIN", "LOGOUT", "REGISTER", "UPDATE_PROFILE", "PASSWORD_RESET"},
    "CHAT":       {"CREATE_CHAT", "VIEW_CHAT", "UPDATE_CHAT", "DELETE_CHAT", "SUBMIT_FOR_REVIEW", "AUTO_SUBMIT_FOR_REVIEW", "AI_RESPONSE_GENERATED"},
    "SPECIALIST": {"ASSIGN_SPECIALIST", "REVIEW_APPROVE", "REVIEW_REJECT", "REVIEW_REQUEST_CHANGES", "SPECIALIST_MESSAGE"},
    "RAG":        {"RAG_ANSWER", "RAG_ERROR", "RAG_REVISE"},
}


def _action_category(action: str) -> str:
    for cat, actions in _ACTION_CATEGORIES.items():
        if action in actions:
            return cat
    return "OTHER"


def list_audit_logs(
    db: Session,
    action: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 200,
) -> list[dict]:
    cache_key = cache_keys.admin_audit_logs(
        action=action.upper() if action else None,
        category=category.upper() if category else None,
        search=search,
        user_id=user_id,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
        limit=limit,
    )
    cached = cache.get_sync(cache_key, resource="admin_audit_logs")
    if cached is not None:
        return cached

    query = db.query(AuditLog)
    if category:
        allowed = _ACTION_CATEGORIES.get(category.upper(), set())
        query = query.filter(AuditLog.action.in_(allowed))
    if action:
        query = query.filter(AuditLog.action == action.upper())
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(AuditLog.action.ilike(term), AuditLog.details.ilike(term)))

    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    result = [
        {
            "id": log.id,
            "user_id": log.user_id,
            "user_identifier": f"{log.user.role.value}_{log.user.id}" if log.user else None,
            "action": log.action,
            "category": _action_category(log.action),
            "details": log.details,
            "timestamp": log.timestamp,
        }
        for log in logs
    ]
    cache.set_sync(
        cache_key,
        result,
        ttl=settings.CACHE_ADMIN_AUDIT_LOG_TTL,
        resource="admin_audit_logs",
    )
    return result

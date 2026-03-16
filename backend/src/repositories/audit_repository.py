from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.db.models import AuditLog
from src.utils.cache import cache, cache_keys


def log(
    db: Session,
    *,
    user_id: int,
    action: str,
    details: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(user_id=user_id, action=action, details=details)
    db.add(entry)
    db.commit()
    cache.delete_pattern_sync(cache_keys.admin_audit_logs_pattern(), resource="admin_audit_logs")
    return entry


async def async_log(
    db: AsyncSession,
    *,
    user_id: int,
    action: str,
    details: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(user_id=user_id, action=action, details=details)
    db.add(entry)
    await db.commit()
    await cache.delete_pattern(
        cache_keys.admin_audit_logs_pattern(),
        resource="admin_audit_logs",
    )
    return entry

from typing import Optional
from sqlalchemy.orm import Session

from src.db.models import AuditLog


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
    return entry

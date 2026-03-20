from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.models.password_reset_token import PasswordResetToken


def create(
    db: Session,
    *,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
) -> PasswordResetToken:
    entry = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_valid_by_hash(
    db: Session,
    *,
    token_hash: str,
    now: datetime,
) -> Optional[PasswordResetToken]:
    return (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .first()
    )


def mark_as_used(
    db: Session, token_row: PasswordResetToken, *, used_at: datetime
) -> PasswordResetToken:
    token_row.used_at = used_at
    db.commit()
    db.refresh(token_row)
    return token_row


def invalidate_active_for_user(db: Session, *, user_id: int, now: datetime) -> int:
    updated = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .update({PasswordResetToken.used_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated

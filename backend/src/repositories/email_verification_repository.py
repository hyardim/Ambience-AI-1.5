from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.db.email_verification_models import EmailVerificationToken


def create(
    db: Session,
    *,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
) -> EmailVerificationToken:
    entry = EmailVerificationToken(
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
) -> Optional[EmailVerificationToken]:
    return (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > now,
        )
        .first()
    )


def mark_as_used(
    db: Session,
    token_row: EmailVerificationToken,
    *,
    used_at: datetime,
) -> EmailVerificationToken:
    token_row.used_at = used_at
    db.commit()
    db.refresh(token_row)
    return token_row


def invalidate_active_for_user(db: Session, *, user_id: int, now: datetime) -> int:
    updated = (
        db.query(EmailVerificationToken)
        .filter(
            EmailVerificationToken.user_id == user_id,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at > now,
        )
        .update({EmailVerificationToken.used_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated

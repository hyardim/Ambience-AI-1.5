from __future__ import annotations

from datetime import timedelta

from src.db.models import User, UserRole
from src.repositories import password_reset_repository
from src.services import auth_service


def _user(db_session, email: str = "reset-repo@example.com") -> User:
    user = User(
        email=email,
        hashed_password="hash",
        full_name="Reset Repo",
        role=UserRole.GP,
        specialty=None,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_cleanup_expired_or_used_removes_old_rows(db_session):
    user = _user(db_session)
    now = auth_service._utcnow()

    expired = password_reset_repository.create(
        db_session,
        user_id=user.id,
        token_hash="expired-hash",
        expires_at=now - timedelta(hours=2),
    )
    used_old = password_reset_repository.create(
        db_session,
        user_id=user.id,
        token_hash="used-old-hash",
        expires_at=now + timedelta(minutes=30),
    )
    used_old.used_at = now - timedelta(days=2)
    db_session.commit()

    keep_fresh = password_reset_repository.create(
        db_session,
        user_id=user.id,
        token_hash="fresh-hash",
        expires_at=now + timedelta(minutes=30),
    )
    expired_id = expired.id
    used_old_id = used_old.id
    keep_fresh_id = keep_fresh.id

    deleted = password_reset_repository.cleanup_expired_or_used(
        db_session,
        older_than=now - timedelta(hours=1),
    )

    assert deleted == 2
    remaining = password_reset_repository.get_valid_by_hash(
        db_session,
        token_hash="fresh-hash",
        now=now,
    )
    assert remaining is not None
    assert remaining.id == keep_fresh_id
    assert expired_id != keep_fresh_id
    assert used_old_id != keep_fresh_id

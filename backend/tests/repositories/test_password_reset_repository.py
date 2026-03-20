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


def test_invalidate_active_for_user(db_session):
    user = _user(db_session)
    now = auth_service._utcnow()

    password_reset_repository.create(
        db_session,
        user_id=user.id,
        token_hash="active-hash",
        expires_at=now + timedelta(minutes=30),
    )
    password_reset_repository.create(
        db_session,
        user_id=user.id,
        token_hash="active-hash-2",
        expires_at=now + timedelta(minutes=30),
    )

    invalidated = password_reset_repository.invalidate_active_for_user(
        db_session,
        user_id=user.id,
        now=now,
    )

    assert invalidated == 2
    remaining = password_reset_repository.get_valid_by_hash(
        db_session,
        token_hash="active-hash",
        now=now,
    )
    assert remaining is None

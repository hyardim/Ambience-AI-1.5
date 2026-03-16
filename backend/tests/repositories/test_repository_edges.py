from __future__ import annotations

import pytest
from src.db.models import AuditLog, ChatStatus, User, UserRole
from src.repositories import audit_repository, chat_repository
from tests.conftest import TestingAsyncSessionLocal


def _user(db_session):
    user = User(
        email="repo@example.com",
        hashed_password="hash",
        full_name="Repo",
        role=UserRole.GP,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_audit_log_can_skip_cache_invalidation(monkeypatch, db_session):
    called = []
    monkeypatch.setattr(
        audit_repository.cache,
        "delete_pattern_sync",
        lambda *args, **kwargs: called.append(True),
    )
    entry = audit_repository.log(
        db_session,
        user_id=1,
        action="TEST",
        invalidate_admin_cache=False,
    )
    assert isinstance(entry, AuditLog)
    assert called == []


@pytest.mark.asyncio
async def test_async_audit_log_can_skip_cache_invalidation(monkeypatch, db_session):
    called = []
    monkeypatch.setattr(
        audit_repository.cache,
        "delete_pattern",
        lambda *args, **kwargs: called.append(True),
    )
    async with TestingAsyncSessionLocal() as session:
        entry = await audit_repository.async_log(
            session,
            user_id=1,
            action="TEST",
            invalidate_admin_cache=False,
        )
    assert entry.action == "TEST"
    assert called == []


@pytest.mark.asyncio
async def test_async_audit_log_invalidates_cache_by_default(monkeypatch, db_session):
    called = []

    async def fake_delete_pattern(*args, **kwargs):
        called.append((args, kwargs))

    monkeypatch.setattr(audit_repository.cache, "delete_pattern", fake_delete_pattern)

    async with TestingAsyncSessionLocal() as session:
        entry = await audit_repository.async_log(
            session,
            user_id=1,
            action="TEST",
        )

    assert entry.action == "TEST"
    assert called


@pytest.mark.asyncio
async def test_chat_repository_async_update(db_session):
    user = _user(db_session)
    chat = chat_repository.create(db_session, user_id=user.id, title="Chat")
    async with TestingAsyncSessionLocal() as session:
        loaded = await chat_repository.async_get(session, chat.id, user_id=user.id)
        assert loaded is not None
        updated = await chat_repository.async_update(
            session, loaded, status=ChatStatus.SUBMITTED
        )
    assert updated.status == ChatStatus.SUBMITTED


def test_chat_repository_archive_sets_flag(db_session):
    user = _user(db_session)
    chat = chat_repository.create(db_session, user_id=user.id, title="Chat")
    chat_repository.archive(db_session, chat)
    assert chat.is_archived is True

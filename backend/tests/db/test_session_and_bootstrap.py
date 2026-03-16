from __future__ import annotations

from contextlib import contextmanager

import pytest
from src.db import bootstrap, session


def test_make_async_url_handles_sqlite():
    assert (
        session._make_async_url("sqlite:///tmp/test.db")
        == "sqlite+aiosqlite:///tmp/test.db"
    )


def test_make_async_url_handles_postgres():
    assert (
        session._make_async_url("postgresql://user:pw@host/db")
        == "postgresql+asyncpg://user:pw@host/db"
    )


def test_get_db_rolls_back_and_closes(monkeypatch):
    events = []

    class FakeSession:
        def rollback(self):
            events.append("rollback")

        def close(self):
            events.append("close")

    monkeypatch.setattr(session, "SessionLocal", lambda: FakeSession())
    gen = session.get_db()
    yielded = next(gen)
    assert yielded.__class__.__name__ == "FakeSession"
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))
    assert events == ["rollback", "close"]


@pytest.mark.asyncio
async def test_get_async_db_rolls_back(monkeypatch):
    events = []

    class FakeAsyncSession:
        async def rollback(self):
            events.append("rollback")

    class FakeFactory:
        async def __aenter__(self):
            return FakeAsyncSession()

        async def __aexit__(self, exc_type, exc, tb):
            events.append("close")

    monkeypatch.setattr(session, "AsyncSessionLocal", lambda: FakeFactory())
    gen = session.get_async_db()
    yielded = await gen.__anext__()
    assert yielded.__class__.__name__ == "FakeAsyncSession"
    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("boom"))
    assert events == ["rollback", "close"]


def test_ensure_default_users_short_circuits_when_disabled(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    called = {"session": 0}
    monkeypatch.setattr(
        bootstrap, "SessionLocal", lambda: called.__setitem__("session", 1)
    )
    bootstrap.ensure_default_users()
    assert called["session"] == 0


def test_ensure_default_users_creates_missing_users(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "AUTH_BOOTSTRAP_DEMO_USERS", True)

    class FakeQuery:
        def __init__(self):
            self.email = None

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False
            self.closed = False

        def query(self, model):
            return FakeQuery()

        def add(self, value):
            self.added.append(value)

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True

    fake_session = FakeSession()
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        bootstrap.security, "get_password_hash", lambda password: f"hash:{password}"
    )

    bootstrap.ensure_default_users()

    assert len(fake_session.added) == 3
    assert fake_session.committed is True
    assert fake_session.closed is True


def test_ensure_default_users_skips_existing(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "AUTH_BOOTSTRAP_DEMO_USERS", True)

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return object()

    class FakeSession:
        def __init__(self):
            self.added = []

        def query(self, model):
            return FakeQuery()

        def add(self, value):
            self.added.append(value)

        def commit(self):
            return None

        def close(self):
            return None

    fake_session = FakeSession()
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: fake_session)
    bootstrap.ensure_default_users()
    assert fake_session.added == []


def test_prepare_database_runs_all_bootstrap_steps(monkeypatch):
    calls = []
    monkeypatch.setattr(
        bootstrap.Base.metadata, "create_all", lambda bind: calls.append("create_all")
    )
    monkeypatch.setattr(bootstrap, "ensure_auth_columns", lambda: calls.append("auth"))
    monkeypatch.setattr(
        bootstrap, "ensure_notification_fk", lambda: calls.append("notif")
    )
    monkeypatch.setattr(
        bootstrap, "ensure_message_columns", lambda: calls.append("message")
    )
    monkeypatch.setattr(
        bootstrap, "ensure_chat_archive_column", lambda: calls.append("archive")
    )
    monkeypatch.setattr(bootstrap, "ensure_chat_columns", lambda: calls.append("chat"))
    monkeypatch.setattr(
        bootstrap, "ensure_enum_columns_lowercase", lambda: calls.append("enum")
    )
    monkeypatch.setattr(
        bootstrap, "ensure_default_users", lambda: calls.append("users")
    )

    bootstrap.prepare_database()

    assert calls == [
        "create_all",
        "auth",
        "notif",
        "message",
        "archive",
        "chat",
        "enum",
        "users",
    ]


def test_ensure_column_helpers_execute_expected_sql(monkeypatch):
    statements = []

    class FakeConnection:
        def execute(self, statement):
            statements.append(str(statement))

    @contextmanager
    def fake_begin():
        yield FakeConnection()

    monkeypatch.setattr(bootstrap.engine, "begin", fake_begin)

    bootstrap.ensure_auth_columns()
    bootstrap.ensure_notification_fk()
    bootstrap.ensure_message_columns()
    bootstrap.ensure_chat_columns()
    bootstrap.ensure_chat_archive_column()
    bootstrap.ensure_enum_columns_lowercase()

    joined = "\n".join(statements)
    assert "ALTER TABLE users ADD COLUMN IF NOT EXISTS role" in joined
    assert "ALTER TABLE notifications" in joined
    assert "ALTER TABLE messages ADD COLUMN IF NOT EXISTS citations JSONB" in joined
    assert "ALTER TABLE chats ADD COLUMN IF NOT EXISTS patient_context JSONB" in joined
    assert "ALTER TABLE chats ADD COLUMN IF NOT EXISTS is_archived BOOLEAN" in joined
    assert "UPDATE users SET role = LOWER(role)" in joined

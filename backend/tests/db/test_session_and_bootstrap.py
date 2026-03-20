from __future__ import annotations

import importlib

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


def test_ensure_default_users_short_circuits_in_production(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "AUTH_BOOTSTRAP_DEMO_USERS", True)
    monkeypatch.setattr(bootstrap.settings, "APP_ENV", "production")
    called = {"session": 0}
    monkeypatch.setattr(
        bootstrap, "SessionLocal", lambda: called.__setitem__("session", 1)
    )

    bootstrap.ensure_default_users()

    assert called["session"] == 0


def test_ensure_default_users_creates_missing_users(monkeypatch):
    monkeypatch.setattr(bootstrap.settings, "AUTH_BOOTSTRAP_DEMO_USERS", True)
    monkeypatch.setattr(bootstrap.settings, "APP_ENV", "development")

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
    monkeypatch.setattr(bootstrap.settings, "APP_ENV", "development")

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


def test_bootstrap_module_reload_sets_expected_paths():
    reloaded = importlib.reload(bootstrap)

    assert reloaded.PROJECT_ROOT.name == "backend"
    assert reloaded.ALEMBIC_INI_PATH.name == "alembic.ini"
    assert reloaded.ALEMBIC_SCRIPT_PATH.name == "alembic"


def test_build_alembic_config_sets_expected_paths_and_url():
    config = bootstrap.build_alembic_config()

    assert config.get_main_option("script_location").endswith("/backend/alembic")
    assert config.get_main_option("sqlalchemy.url") == bootstrap.settings.DATABASE_URL


def test_run_migrations_upgrades_to_head(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "build_alembic_config", lambda: "cfg")
    monkeypatch.setattr(
        bootstrap.command,
        "upgrade",
        lambda cfg, target: calls.append((cfg, target)),
    )

    bootstrap.run_migrations()

    assert calls == [("cfg", "head")]


def test_prepare_database_runs_migrations_then_bootstraps_users(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "run_migrations", lambda: calls.append("migrate"))
    monkeypatch.setattr(
        bootstrap, "ensure_default_users", lambda: calls.append("users")
    )

    bootstrap.prepare_database()

    assert calls == ["migrate", "users"]


def test_main_runs_migrate(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "run_migrations", lambda: calls.append("migrate"))

    bootstrap.main(["migrate"])

    assert calls == ["migrate"]


def test_main_runs_seed_demo_users(monkeypatch):
    calls = []
    monkeypatch.setattr(
        bootstrap, "ensure_default_users", lambda: calls.append("seed-demo-users")
    )

    bootstrap.main(["seed-demo-users"])

    assert calls == ["seed-demo-users"]


def test_main_runs_prepare(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap, "prepare_database", lambda: calls.append("prepare"))

    bootstrap.main(["prepare"])

    assert calls == ["prepare"]

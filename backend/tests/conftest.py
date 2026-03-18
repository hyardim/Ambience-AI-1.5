"""
Shared test fixtures for the Ambience-AI-1.5 backend test suite.

Uses a file-based temp SQLite database so that the synchronous and
asynchronous engines share the same data store (in-memory SQLite would
give each engine its own private database).
The `get_db` and `get_async_db` dependencies are overridden for every
test, and the schema is created fresh and torn down after each test
function.
"""

import atexit
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# SQLite has no native JSONB type. Teach the SQLite type compiler to render
# JSONB columns as plain JSON so that Base.metadata.create_all() works against
# the in-memory test database without modifying production models.
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from src.db.base import Base
import src.db.password_reset_models  # noqa: F401
from src.db.session import get_async_db, get_db
from src.api import auth, chats, specialist, admin, notifications
from src.services import auth_service

# ---------------------------------------------------------------------------
# File-based temp SQLite shared by the sync and async engines so that data
# committed through one engine is visible to the other.
# ---------------------------------------------------------------------------
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)
_test_db_path = _test_db_path.replace("\\", "/")


def _cleanup_test_db():
    try:
        os.unlink(_test_db_path)
    except OSError:
        pass


atexit.register(_cleanup_test_db)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{_test_db_path}"
ASYNC_SQLALCHEMY_DATABASE_URL = f"sqlite+aiosqlite:///{_test_db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingAsyncSessionLocal = sessionmaker(
    bind=async_engine, class_=AsyncSession, expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    """Create a minimal FastAPI app with only the routers under test."""
    app = FastAPI()
    app.include_router(auth.router,          prefix="/auth",          tags=["auth"])
    app.include_router(chats.router,         prefix="/chats",         tags=["chats"])
    app.include_router(specialist.router,    prefix="/specialist",    tags=["specialist"])
    app.include_router(admin.router,         prefix="/admin",         tags=["admin"])
    app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])

    @app.get("/health")
    def health_check():
        return {"status": "healthy", "system": "Ambience-AI-1.5"}

    return app


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    """Create all tables before the test, drop them after."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_forgot_password_rate_limit_state():
    auth_service._forgot_password_attempts.clear()
    yield
    auth_service._forgot_password_attempts.clear()


@pytest.fixture()
def client(db_session, monkeypatch):
    """HTTP test client wired to the file-based test database."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # session lifecycle managed by db_session fixture

    async def override_get_async_db():
        async with TestingAsyncSessionLocal() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    # Ensure the background AI generation also uses the test async session
    import src.services.chat_service as _cs
    monkeypatch.setattr(_cs, "AsyncSessionLocal", TestingAsyncSessionLocal)

    app = _build_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# User data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def gp_user_payload():
    return {
        "first_name": "Alice",
        "last_name": "GP",
        "full_name": "Alice GP",
        "email": "alice.gp@nhs.uk",
        "password": "SecurePass123!",
        "role": "gp",
    }


@pytest.fixture()
def specialist_user_payload():
    return {
        "first_name": "Bob",
        "last_name": "Specialist",
        "email": "bob.specialist@nhs.uk",
        "password": "SecurePass123!",
        "role": "specialist",
        "specialty": "neurology",
    }


@pytest.fixture()
def admin_user_payload():
    return {
        "first_name": "Admin",
        "last_name": "User",
        "email": "admin@nhs.uk",
        "password": "AdminPass123!",
        "role": "admin",
    }


@pytest.fixture()
def second_gp_payload():
    return {
        "first_name": "Carol",
        "last_name": "Other",
        "email": "carol.other@nhs.uk",
        "password": "AnotherPass456!",
        "role": "gp",
    }


# ---------------------------------------------------------------------------
# Pre-registered user + token fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registered_gp(client, gp_user_payload):
    """Register a GP user and return the full AuthResponse JSON."""
    resp = client.post("/auth/register", json=gp_user_payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def registered_specialist(client, specialist_user_payload):
    """Register a specialist user and return the full AuthResponse JSON."""
    resp = client.post("/auth/register", json=specialist_user_payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def registered_admin(client, admin_user_payload):
    """Register an admin user and return the full AuthResponse JSON."""
    resp = client.post("/auth/register", json=admin_user_payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def registered_second_gp(client, second_gp_payload):
    """Register a second GP user (for ownership isolation tests)."""
    resp = client.post("/auth/register", json=second_gp_payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture()
def gp_headers(registered_gp):
    """Bearer token headers for the GP user."""
    return {"Authorization": f"Bearer {registered_gp['access_token']}"}


@pytest.fixture()
def specialist_headers(registered_specialist):
    """Bearer token headers for the specialist user."""
    return {"Authorization": f"Bearer {registered_specialist['access_token']}"}


@pytest.fixture()
def admin_headers(registered_admin):
    """Bearer token headers for the admin user."""
    return {"Authorization": f"Bearer {registered_admin['access_token']}"}


@pytest.fixture()
def second_gp_headers(registered_second_gp):
    """Bearer token headers for the second GP user."""
    return {"Authorization": f"Bearer {registered_second_gp['access_token']}"}


# ---------------------------------------------------------------------------
# Chat fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def created_chat(client, gp_headers):
    """Create a chat owned by the GP user and return the ChatResponse JSON."""
    resp = client.post("/chats/", json={"title": "Test Chat", "specialty": "neurology"}, headers=gp_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def submitted_chat(client, gp_headers):
    """Create a neurology chat and auto-submit it by sending a message."""
    chat = client.post(
        "/chats/", json={"title": "Submitted Chat", "specialty": "neurology"}, headers=gp_headers
    ).json()
    client.post(
        f"/chats/{chat['id']}/message",
        json={"role": "user", "content": "Patient has wrist pain and swelling."},
        headers=gp_headers,
    )
    # Sending the first message auto-submits the chat to SUBMITTED status.
    return client.get(f"/chats/{chat['id']}", headers=gp_headers).json()

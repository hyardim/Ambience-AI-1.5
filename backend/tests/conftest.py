"""
Shared test fixtures for the Ambience-AI-1.5 backend test suite.

Uses an in-memory SQLite database so no PostgreSQL connection is needed.
The `get_db` dependency is overridden for every test, and the schema is
created fresh and torn down after each test function.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.base import Base
from src.db.session import get_db
from src.api import auth, chats

# ---------------------------------------------------------------------------
# In-memory SQLite engine (no file, no external service required)
# ---------------------------------------------------------------------------
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app() -> FastAPI:
    """Create a minimal FastAPI app with only the routers under test."""
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(chats.router, prefix="/chats", tags=["chats"])

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


@pytest.fixture()
def client(db_session):
    """HTTP test client wired to the in-memory database."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass  # session lifecycle managed by db_session fixture

    app = _build_app()
    app.dependency_overrides[get_db] = override_get_db

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
def second_gp_headers(registered_second_gp):
    """Bearer token headers for the second GP user."""
    return {"Authorization": f"Bearer {registered_second_gp['access_token']}"}


# ---------------------------------------------------------------------------
# Chat fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def created_chat(client, gp_headers):
    """Create a chat owned by the GP user and return the ChatResponse JSON."""
    resp = client.post("/chats/", json={"title": "Test Chat"}, headers=gp_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()

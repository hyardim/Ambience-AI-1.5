from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.core import security
from src.core.config import settings
from src.db.models import UserRole


def test_authenticate_user_returns_false_when_missing(monkeypatch):
    db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: None)
        )
    )
    assert security.authenticate_user(db, "missing@example.com", "pw") is False


def test_authenticate_user_returns_false_on_bad_password(monkeypatch):
    user = SimpleNamespace(hashed_password="hashed")
    db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: user)
        )
    )
    monkeypatch.setattr(security, "verify_password", lambda plain, hashed: False)
    assert security.authenticate_user(db, "user@example.com", "pw") is False


def test_authenticate_user_returns_user_on_success(monkeypatch):
    user = SimpleNamespace(hashed_password="hashed")
    db = SimpleNamespace(
        query=lambda model: SimpleNamespace(
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: user)
        )
    )
    monkeypatch.setattr(security, "verify_password", lambda plain, hashed: True)
    assert security.authenticate_user(db, "user@example.com", "pw") is user


def test_decode_token_rejects_missing_subject():
    token = security.create_access_token({"role": "gp"})
    with pytest.raises(HTTPException) as exc:
        security.decode_token(token)
    assert exc.value.status_code == 401


def test_get_current_user_rejects_missing_subject():
    token = security.create_access_token({"role": "gp"})
    with pytest.raises(HTTPException) as exc:
        security.get_current_user(token)
    assert exc.value.status_code == 401
    assert exc.value.headers == {"WWW-Authenticate": "Bearer"}


def test_decode_token_rejects_invalid_token():
    with pytest.raises(HTTPException):
        security.decode_token("not-a-jwt")


def test_decode_token_returns_subject_for_valid_access_token():
    token = security.create_access_token({"sub": "ok@example.com"})
    assert security.decode_token(token) == "ok@example.com"


def test_decode_token_rejects_refresh_token():
    token = security.create_refresh_token({"sub": "user@example.com"})
    with pytest.raises(HTTPException) as exc:
        security.decode_token(token)
    assert exc.value.status_code == 401


def test_get_request_token_prefers_bearer_token():
    request = SimpleNamespace(cookies={settings.ACCESS_COOKIE_NAME: "cookie-token"})
    assert security._get_request_token(request, "bearer-token") == "bearer-token"


def test_get_request_token_reads_access_cookie():
    request = SimpleNamespace(cookies={settings.ACCESS_COOKIE_NAME: "cookie-token"})
    assert security._get_request_token(request, None) == "cookie-token"


def test_get_refresh_cookie_reads_cookie():
    request = SimpleNamespace(cookies={settings.REFRESH_COOKIE_NAME: "refresh-token"})
    assert security._get_refresh_cookie(request) == "refresh-token"


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({"sub": "user@example.com", "type": "refresh"}, "access"),
        ({"sub": None, "type": "access"}, "access"),
        ({"sub": "user@example.com", "type": "access", "sv": "1"}, "access"),
    ],
)
def test_validate_payload_rejects_invalid_payload(payload, expected_type):
    with pytest.raises(HTTPException) as exc:
        security._validate_payload(payload, expected_type=expected_type)
    assert exc.value.status_code == 401


def test_resolve_user_from_token_rejects_missing_user(db_session):
    token = security.create_access_token({"sub": "missing@example.com"})
    with pytest.raises(HTTPException) as exc:
        security._resolve_user_from_token(db_session, token, expected_type="access")
    assert exc.value.status_code == 401


def test_resolve_user_from_token_rejects_session_version_mismatch(db_session):
    from src.db.models import User

    user = User(
        email="sv@example.com",
        hashed_password="hash",
        full_name="SV",
        role=UserRole.GP,
        specialty=None,
        is_active=True,
        session_version=2,
    )
    db_session.add(user)
    db_session.commit()
    token = security.create_access_token(
        {"sub": user.email, "sv": 1, "role": user.role.value}
    )
    with pytest.raises(HTTPException) as exc:
        security._resolve_user_from_token(db_session, token, expected_type="access")
    assert exc.value.status_code == 401


def test_get_current_user_from_cookie_or_header_rejects_missing_token(db_session):
    request = SimpleNamespace(cookies={})
    with pytest.raises(HTTPException) as exc:
        security.get_current_user_from_cookie_or_header(
            request=request, db=db_session, bearer_token=None
        )
    assert exc.value.status_code == 401


def test_get_refresh_user_rejects_missing_cookie(db_session):
    request = SimpleNamespace(cookies={})
    with pytest.raises(HTTPException) as exc:
        security.get_refresh_user(request=request, db=db_session)
    assert exc.value.status_code == 401


def test_get_user_from_access_token_returns_user(db_session):
    from src.db.models import User

    user = User(
        email="access@example.com",
        hashed_password="hash",
        full_name="Access User",
        role=UserRole.GP,
        specialty=None,
        is_active=True,
        session_version=0,
    )
    db_session.add(user)
    db_session.commit()
    token = security.create_access_token_for_user(user)
    resolved = security.get_user_from_access_token(db_session, token)
    assert resolved.email == user.email


def test_set_auth_cookies_sets_both_tokens():
    from fastapi import FastAPI, Response

    app = FastAPI()

    @app.get("/cookies")
    def get_cookies():
        response = Response()
        security.set_auth_cookies(
            response,
            access_token="access-token",
            refresh_token="refresh-token",
        )
        return response

    client = TestClient(app)
    response = client.get("/cookies")
    header = response.headers.get("set-cookie", "")
    assert settings.ACCESS_COOKIE_NAME in header
    assert settings.REFRESH_COOKIE_NAME in header

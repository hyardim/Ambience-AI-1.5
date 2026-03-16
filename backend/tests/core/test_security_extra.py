from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from src.core import security


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

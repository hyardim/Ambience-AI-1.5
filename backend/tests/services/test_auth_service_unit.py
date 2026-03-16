from __future__ import annotations

import pytest
from fastapi import HTTPException
from src.db.models import User, UserRole
from src.schemas.auth import PasswordResetRequest, ProfileUpdate, UserRegister
from src.services import auth_service


def _user(db_session, *, email="user@example.com", active=True):
    user = User(
        email=email,
        hashed_password="hashed",
        full_name="User",
        role=UserRole.GP,
        specialty=None,
        is_active=active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_register_rejects_invalid_role(db_session):
    with pytest.raises(HTTPException) as exc:
        auth_service.register(
            db_session,
            UserRegister(
                email="new@example.com", password="StrongPass1!", role="ghost"
            ),
        )
    assert exc.value.status_code == 400


def test_reset_password_returns_generic_message_for_unknown_user(db_session):
    result = auth_service.reset_password(
        db_session,
        PasswordResetRequest(email="missing@example.com", new_password="StrongPass1!"),
    )
    assert "registered" in result["message"]


def test_reset_password_rejects_deactivated_user(db_session):
    _user(db_session, active=False)
    with pytest.raises(HTTPException) as exc:
        auth_service.reset_password(
            db_session,
            PasswordResetRequest(email="user@example.com", new_password="StrongPass1!"),
        )
    assert exc.value.status_code == 400


def test_logout_returns_message(db_session):
    user = _user(db_session)
    assert auth_service.logout(db_session, user) == {
        "message": "Logged out successfully"
    }


def test_update_profile_requires_current_password_when_setting_new_one(db_session):
    user = _user(db_session)
    with pytest.raises(HTTPException) as exc:
        auth_service.update_profile(
            db_session,
            user,
            ProfileUpdate(new_password="StrongPass1!"),
        )
    assert exc.value.status_code == 400


def test_update_profile_rejects_wrong_current_password(monkeypatch, db_session):
    user = _user(db_session)
    monkeypatch.setattr(
        auth_service.security, "verify_password", lambda plain, hashed: False
    )
    with pytest.raises(HTTPException) as exc:
        auth_service.update_profile(
            db_session,
            user,
            ProfileUpdate(current_password="wrong", new_password="StrongPass1!"),
        )
    assert exc.value.status_code == 400

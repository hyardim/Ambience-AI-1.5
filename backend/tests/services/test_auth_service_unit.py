from __future__ import annotations

import sys
import types
from collections import defaultdict
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.db.models import User, UserRole
from src.schemas.auth import (
    EmailVerificationConfirmRequest,
    ForgotPasswordRequest,
    PasswordResetConfirmRequest,
    ProfileUpdate,
    UserRegister,
)
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
    with pytest.raises(ValidationError):
        UserRegister(email="new@example.com", password="StrongPass1!", role="ghost")


def test_forgot_password_returns_generic_message_for_unknown_user(db_session):
    result = auth_service.forgot_password(
        db_session,
        ForgotPasswordRequest(email="missing@example.com"),
    )
    assert "registered" in result["message"]


def test_forgot_password_returns_generic_message_for_deactivated_user(db_session):
    _user(db_session, active=False)
    result = auth_service.forgot_password(
        db_session,
        ForgotPasswordRequest(email="user@example.com"),
    )
    assert "registered" in result["message"]


def test_forgot_password_returns_generic_message_for_unverified_user(
    monkeypatch, db_session
):
    user = _user(db_session)
    user.email_verified = False
    db_session.commit()

    created = []
    monkeypatch.setattr(
        auth_service.password_reset_repository,
        "create",
        lambda *args, **kwargs: created.append(True),
    )

    result = auth_service.forgot_password(
        db_session,
        ForgotPasswordRequest(email=user.email),
    )

    assert "registered" in result["message"]
    assert created == []


def test_logout_returns_message(db_session):
    user = _user(db_session)
    assert auth_service.logout(db_session, user) == {
        "message": "Logged out successfully"
    }


def test_refresh_returns_auth_response(db_session):
    user = _user(db_session)
    result = auth_service.refresh(user)
    assert result.user.email == user.email
    assert result.token_type == "bearer"
    assert result.access_token


def test_register_normalizes_email_before_storage(db_session, monkeypatch):
    monkeypatch.setattr(
        auth_service.settings, "NEW_USERS_REQUIRE_EMAIL_VERIFICATION", False
    )

    result = auth_service.register(
        db_session,
        UserRegister(
            email="Mixed.Case@Example.com ",
            password="StrongPass1!",
            role="gp",
        ),
    )

    assert result.user.email == "mixed.case@example.com"


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "alllowercase1!",
        "ALLUPPERCASE1!",
        "NoDigits!!",
        "NoSpecial1",
    ],
)
def test_validate_password_rejects_weak_passwords(password):
    with pytest.raises(HTTPException) as exc:
        auth_service._validate_password(password)
    assert exc.value.status_code == 400


def test_validate_password_accepts_strong_password():
    auth_service._validate_password("StrongPass1!")


def test_login_rejects_invalid_email_format(db_session):
    with pytest.raises(HTTPException) as exc:
        auth_service.login(db_session, "not-an-email", "StrongPass1!")

    assert exc.value.status_code == 400
    assert exc.value.detail == "Please enter a valid email address"


def test_profile_update_accepts_explicit_none_new_password():
    payload = ProfileUpdate(new_password=None)
    assert payload.new_password is None


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


def test_resend_verification_returns_generic_for_verified_user(db_session):
    user = _user(db_session)
    user.email_verified = True
    db_session.commit()

    result = auth_service.resend_verification_email(
        db_session,
        SimpleNamespace(email=user.email),
    )

    assert "verification" in result["message"].lower()


def test_forgot_password_returns_generic_when_rate_limited(monkeypatch, db_session):
    monkeypatch.setattr(
        auth_service, "_is_forgot_password_rate_limited", lambda _e: True
    )

    result = auth_service.forgot_password(
        db_session,
        ForgotPasswordRequest(email="limited@example.com"),
    )

    assert "registered" in result["message"]


def test_confirm_email_verification_rejects_deactivated_user(monkeypatch, db_session):
    inactive = _user(db_session, active=False)
    token_row = SimpleNamespace(user=inactive, token_hash="token-hash")

    monkeypatch.setattr(
        auth_service.email_verification_repository,
        "get_valid_by_hash",
        lambda *_args, **_kwargs: token_row,
    )
    monkeypatch.setattr(
        auth_service.security,
        "verify_email_verification_token",
        lambda *_args, **_kwargs: True,
    )

    with pytest.raises(HTTPException) as exc:
        auth_service.confirm_email_verification(
            db_session,
            EmailVerificationConfirmRequest(token="raw-token"),
        )

    assert exc.value.status_code == 400
    assert "deactivated" in exc.value.detail.lower()


def test_reset_password_confirm_rejects_deactivated_user(monkeypatch, db_session):
    inactive = _user(db_session, active=False)
    token_row = SimpleNamespace(user=inactive, token_hash="token-hash")

    monkeypatch.setattr(
        auth_service.password_reset_repository,
        "get_valid_by_hash",
        lambda *_args, **_kwargs: token_row,
    )
    monkeypatch.setattr(
        auth_service.security,
        "verify_password_reset_token",
        lambda *_args, **_kwargs: True,
    )

    with pytest.raises(HTTPException) as exc:
        auth_service.reset_password_confirm(
            db_session,
            PasswordResetConfirmRequest(token="raw-token", new_password="StrongPass1!"),
        )

    assert exc.value.status_code == 400
    assert "deactivated" in exc.value.detail.lower()


def test_reset_password_confirm_rejects_unverified_user(monkeypatch, db_session):
    user = _user(db_session)
    user.email_verified = False
    db_session.commit()
    token_row = SimpleNamespace(user=user, token_hash="token-hash")

    monkeypatch.setattr(
        auth_service.password_reset_repository,
        "get_valid_by_hash",
        lambda *_args, **_kwargs: token_row,
    )
    monkeypatch.setattr(
        auth_service.security,
        "verify_password_reset_token",
        lambda *_args, **_kwargs: True,
    )

    with pytest.raises(HTTPException) as exc:
        auth_service.reset_password_confirm(
            db_session,
            PasswordResetConfirmRequest(token="raw-token", new_password="StrongPass1!"),
        )

    assert exc.value.status_code == 400
    assert "invalid or expired" in exc.value.detail.lower()


def test_get_verification_status_returns_payload(db_session):
    user = _user(db_session)

    result = auth_service.get_verification_status(user)

    assert result["email"] == user.email
    assert result["email_verified"] == user.email_verified


def test_is_rate_limited_falls_back_when_redis_command_errors(monkeypatch):
    class BrokenRedis:
        def incr(self, _key):
            raise RuntimeError("redis write failed")

    monkeypatch.setattr(auth_service, "_get_auth_redis", lambda: BrokenRedis())
    attempts: dict[str, list] = defaultdict(list)

    first = auth_service._is_rate_limited(
        key="limit@example.com",
        redis_prefix="forgot_pw",
        attempts=attempts,
        window_seconds=60,
        max_attempts=1,
    )
    second = auth_service._is_rate_limited(
        key="limit@example.com",
        redis_prefix="forgot_pw",
        attempts=attempts,
        window_seconds=60,
        max_attempts=1,
    )

    assert first is False
    assert second is True


def test_get_auth_redis_initialises_and_caches_client(monkeypatch):
    pinged = {"value": 0}

    class FakeClient:
        def ping(self):
            pinged["value"] += 1

    client = FakeClient()

    class FakeRedisClass:
        @staticmethod
        def from_url(url, decode_responses, socket_connect_timeout):
            assert decode_responses is True
            assert socket_connect_timeout == 2
            return client

    monkeypatch.setattr(auth_service.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(auth_service, "_auth_redis_client", None)
    monkeypatch.setattr(auth_service, "_auth_redis_attempted", False)
    monkeypatch.setitem(
        sys.modules, "redis", types.SimpleNamespace(Redis=FakeRedisClass)
    )

    assert auth_service._get_auth_redis() is client
    assert auth_service._get_auth_redis() is client
    assert pinged["value"] == 1


def test_get_auth_redis_returns_none_when_unavailable(monkeypatch, caplog):
    class FakeRedisClass:
        @staticmethod
        def from_url(url, decode_responses, socket_connect_timeout):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(auth_service.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(auth_service, "_auth_redis_client", None)
    monkeypatch.setattr(auth_service, "_auth_redis_attempted", False)
    monkeypatch.setitem(
        sys.modules, "redis", types.SimpleNamespace(Redis=FakeRedisClass)
    )

    with caplog.at_level("WARNING"):
        assert auth_service._get_auth_redis() is None

    assert "using in-process fallback" in caplog.text


def test_redis_rate_limited_sets_expiry_on_first_hit(monkeypatch):
    events = []

    class FakeRedis:
        def incr(self, key):
            events.append(("incr", key))
            return 1

        def expire(self, key, ttl):
            events.append(("expire", key, ttl))

    monkeypatch.setattr(auth_service, "_get_auth_redis", lambda: FakeRedis())

    assert auth_service._redis_rate_limited("key", 60, 2) is False
    assert events == [("incr", "key"), ("expire", "key", 60)]


def test_is_rate_limited_returns_redis_result_without_local_fallback(monkeypatch):
    attempts: dict[str, list] = defaultdict(list)
    monkeypatch.setattr(auth_service, "_redis_rate_limited", lambda *args: True)

    assert (
        auth_service._is_rate_limited(
            key="limit@example.com",
            redis_prefix="forgot_pw",
            attempts=attempts,
            window_seconds=60,
            max_attempts=1,
        )
        is True
    )
    assert attempts == {}


def test_reset_password_confirm_rejects_reusing_current_password(
    monkeypatch, db_session
):
    user = _user(db_session)
    token_row = SimpleNamespace(user=user, token_hash="token-hash")

    monkeypatch.setattr(
        auth_service.password_reset_repository,
        "get_valid_by_hash",
        lambda *_args, **_kwargs: token_row,
    )
    monkeypatch.setattr(
        auth_service.security,
        "verify_password_reset_token",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        auth_service.security,
        "verify_password",
        lambda plain, hashed: True,
    )

    with pytest.raises(HTTPException) as exc:
        auth_service.reset_password_confirm(
            db_session,
            PasswordResetConfirmRequest(token="raw-token", new_password="StrongPass1!"),
        )

    assert exc.value.status_code == 400
    assert "different from current password" in exc.value.detail.lower()

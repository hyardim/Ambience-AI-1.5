import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core import security
from src.core.config import settings
from src.db.models import User, UserRole
from src.repositories import (
    audit_repository,
    email_verification_repository,
    password_reset_repository,
    user_repository,
)
from src.schemas.auth import (
    AuthResponse,
    EmailVerificationConfirmRequest,
    EmailVerificationResendRequest,
    ForgotPasswordRequest,
    PasswordResetConfirmRequest,
    ProfileUpdate,
    RegisterResponse,
    UserOut,
    UserRegister,
)
from src.services import email_service
from src.utils.cache import cache, cache_keys

GENERIC_FORGOT_PASSWORD_MESSAGE = {
    "message": "If that email is registered, a password reset link will be sent shortly"
}
GENERIC_RESEND_VERIFICATION_MESSAGE = {
    "message": "If an account exists and requires verification, a verification link will be sent shortly"
}
GENERIC_RESET_SUCCESS_MESSAGE = {"message": "Password reset successful"}
GENERIC_VERIFY_SUCCESS_MESSAGE = {"message": "Email verified successfully"}
SAFE_INVALID_RESET_TOKEN_MESSAGE = "Invalid or expired reset token"
SAFE_INVALID_VERIFICATION_TOKEN_MESSAGE = "Invalid or expired verification token"

# In-process fallback rate-limit dicts (used only when Redis is unavailable).
_forgot_password_attempts: dict[str, list[datetime]] = defaultdict(list)
_resend_verification_attempts: dict[str, list[datetime]] = defaultdict(list)
logger = logging.getLogger(__name__)

# Lazy-loaded sync Redis client for auth rate limiting.
_auth_redis_client = None
_auth_redis_attempted = False


def _get_auth_redis():
    """Return a sync Redis client, or None if unavailable."""
    global _auth_redis_client, _auth_redis_attempted
    if _auth_redis_attempted:
        return _auth_redis_client
    _auth_redis_attempted = True
    if not settings.CACHE_ENABLED:
        return None
    try:
        import redis

        _auth_redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        _auth_redis_client.ping()
    except Exception as exc:
        logger.warning(
            "Auth rate limiter: Redis unavailable (%s) — using in-process fallback",
            exc,
        )
        _auth_redis_client = None
    return _auth_redis_client


def _utcnow() -> datetime:
    # Store UTC consistently while keeping naive datetimes for DB compatibility.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _redis_rate_limited(
    redis_key: str,
    window_seconds: int,
    max_attempts: int,
) -> bool | None:
    """Check and increment a rate-limit counter in Redis.

    Uses the same atomic INCR pattern as the global rate limiter: increment
    first, set TTL only on the first request so the window is not reset.
    """
    client = _get_auth_redis()
    if client is None:
        return None  # caller will fall through to in-process check

    try:
        count = client.incr(redis_key)
        if count == 1:
            client.expire(redis_key, window_seconds)
        return count > max_attempts
    except Exception as exc:
        logger.warning("Auth rate-limit Redis error: %s", exc)
        return None  # fall through to in-process


def _is_rate_limited(
    *,
    key: str,
    redis_prefix: str,
    attempts: dict[str, list[datetime]],
    window_seconds: int,
    max_attempts: int,
) -> bool:
    # Hash the email so we don't store PII in Redis keys.
    hashed = hashlib.sha256(key.lower().encode()).hexdigest()[:16]
    redis_key = f"auth_rl:{redis_prefix}:{hashed}"
    redis_limited = _redis_rate_limited(redis_key, window_seconds, max_attempts)
    if redis_limited is not None:
        return redis_limited

    # In-process fallback (single-worker only).
    now = _utcnow()
    window_start = now - timedelta(seconds=window_seconds)
    bucket = attempts[key.lower()]
    bucket[:] = [stamp for stamp in bucket if stamp >= window_start]
    if len(bucket) >= max_attempts:
        return True
    bucket.append(now)
    return False


def _is_forgot_password_rate_limited(email: str) -> bool:
    return _is_rate_limited(
        key=email,
        redis_prefix="forgot_pw",
        attempts=_forgot_password_attempts,
        window_seconds=settings.FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts=settings.FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS,
    )


def _is_resend_verification_rate_limited(email: str) -> bool:
    return _is_rate_limited(
        key=email,
        redis_prefix="resend_verify",
        attempts=_resend_verification_attempts,
        window_seconds=settings.RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts=settings.RESEND_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS,
    )


def _validate_password(password: str) -> None:
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("a lowercase letter")
    if not re.search(r"\d", password):
        errors.append("a digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("a special character")
    if errors:
        raise HTTPException(
            status_code=400, detail=f"Password must contain: {', '.join(errors)}"
        )


def _make_auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=security.create_access_token_for_user(user),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


def _issue_verification_link(db: Session, user: User, now: datetime) -> None:

    email_verification_repository.invalidate_active_for_user(
        db, user_id=user.id, now=now
    )

    raw_token = security.generate_email_verification_token()
    token_hash = security.hash_email_verification_token(raw_token)
    expires_at = now + timedelta(minutes=settings.EMAIL_VERIFICATION_TOKEN_TTL_MINUTES)

    email_verification_repository.create(
        db,
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    verify_link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-email?token={quote(raw_token)}"
    email_service.send_verification_email(user.email, verify_link)
    audit_repository.log(
        db,
        user_id=user.id,
        action="EMAIL_VERIFICATION_SENT",
        details=f"user_id={user.id}",
    )


def login(db: Session, email: str, password: str) -> AuthResponse:
    user = user_repository.get_by_email(db, email)
    if not user or not security.verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is deactivated")

    if not user.email_verified and not settings.ALLOW_LEGACY_UNVERIFIED_LOGIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in. You can request a new verification email.",
        )

    audit_repository.log(
        db, user_id=user.id, action="LOGIN", details=f"user_id={user.id}"
    )
    return _make_auth_response(user)


def register(db: Session, payload: UserRegister) -> RegisterResponse:
    if user_repository.get_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    role = UserRole(payload.role)

    if role == UserRole.SPECIALIST and not payload.specialty:
        raise HTTPException(
            status_code=400, detail="Specialists must provide a specialty"
        )

    _validate_password(payload.password)

    now = _utcnow()
    requires_verification = settings.NEW_USERS_REQUIRE_EMAIL_VERIFICATION
    user = user_repository.create(
        db,
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=payload.full_name,
        role=role,
        specialty=payload.specialty,
        email_verified=not requires_verification,
        email_verified_at=None if requires_verification else now,
    )

    audit_repository.log(
        db, user_id=user.id, action="REGISTER", details=f"user_id={user.id}"
    )

    if requires_verification:
        audit_repository.log(
            db,
            user_id=user.id,
            action="EMAIL_VERIFICATION_REQUESTED",
            details=f"user_id={user.id} source=register",
        )
        try:
            _issue_verification_link(db, user, now)
        except Exception as exc:  # pragma: no cover - defensive email transport path
            logger.exception(
                "Verification email dispatch failed during register for user_id=%s: %s",
                user.id,
                exc,
            )
        return RegisterResponse(
            user=UserOut.model_validate(user),
            requires_email_verification=True,
            message="Registration successful. Please verify your email to continue.",
        )

    auth = _make_auth_response(user)
    return RegisterResponse(
        access_token=auth.access_token,
        token_type=auth.token_type,
        user=auth.user,
        requires_email_verification=False,
        message="Registration successful",
    )


def resend_verification_email(
    db: Session, payload: EmailVerificationResendRequest
) -> dict:
    if _is_resend_verification_rate_limited(payload.email):
        return GENERIC_RESEND_VERIFICATION_MESSAGE

    user = user_repository.get_by_email(db, payload.email)
    if not user:
        audit_repository.log(
            db,
            user_id=None,
            action="EMAIL_VERIFICATION_REQUESTED",
            details="user_id=unknown source=resend",
        )
        return GENERIC_RESEND_VERIFICATION_MESSAGE

    audit_repository.log(
        db,
        user_id=user.id,
        action="EMAIL_VERIFICATION_REQUESTED",
        details=f"user_id={user.id} source=resend",
    )

    if not user.is_active or user.email_verified:
        return GENERIC_RESEND_VERIFICATION_MESSAGE

    try:
        _issue_verification_link(db, user, _utcnow())
    except Exception as exc:  # pragma: no cover - defensive email transport path
        logger.exception(
            "Verification email dispatch failed during resend for user_id=%s: %s",
            user.id,
            exc,
        )

    return GENERIC_RESEND_VERIFICATION_MESSAGE


def confirm_email_verification(
    db: Session, payload: EmailVerificationConfirmRequest
) -> dict:
    now = _utcnow()
    token_hash = security.hash_email_verification_token(payload.token)
    token_row = email_verification_repository.get_valid_by_hash(
        db, token_hash=token_hash, now=now
    )

    if not token_row or not security.verify_email_verification_token(
        payload.token, token_row.token_hash
    ):
        raise HTTPException(
            status_code=400, detail=SAFE_INVALID_VERIFICATION_TOKEN_MESSAGE
        )

    user = token_row.user
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Account is deactivated")

    if not user.email_verified:
        user_repository.update(
            db,
            user,
            email_verified=True,
            email_verified_at=now,
        )
        cache.delete_sync(
            cache_keys.user_profile(user.id),
            user_id=user.id,
            resource="user_profile",
        )
        audit_repository.log(
            db,
            user_id=user.id,
            action="EMAIL_VERIFIED",
            details=f"user_id={user.id}",
        )

    email_verification_repository.mark_as_used(db, token_row, used_at=now)
    return GENERIC_VERIFY_SUCCESS_MESSAGE


def forgot_password(db: Session, payload: ForgotPasswordRequest) -> dict:
    if _is_forgot_password_rate_limited(payload.email):
        return GENERIC_FORGOT_PASSWORD_MESSAGE

    user = user_repository.get_by_email(db, payload.email)
    if not user:
        audit_repository.log(
            db,
            user_id=None,
            action="PASSWORD_RESET_REQUESTED",
            details="user_id=unknown",
        )
        return GENERIC_FORGOT_PASSWORD_MESSAGE

    if not user.is_active:
        audit_repository.log(
            db,
            user_id=user.id,
            action="PASSWORD_RESET_REQUESTED",
            details=f"user_id={user.id} inactive=true",
        )
        return GENERIC_FORGOT_PASSWORD_MESSAGE

    if not user.email_verified:
        audit_repository.log(
            db,
            user_id=user.id,
            action="PASSWORD_RESET_REQUESTED",
            details=f"user_id={user.id} email_unverified=true",
        )
        return GENERIC_FORGOT_PASSWORD_MESSAGE

    now = _utcnow()

    password_reset_repository.invalidate_active_for_user(db, user_id=user.id, now=now)

    raw_token = security.generate_password_reset_token()
    token_hash = security.hash_password_reset_token(raw_token)
    expires_at = now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_TTL_MINUTES)
    password_reset_repository.create(
        db,
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    reset_link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={quote(raw_token)}"
    try:
        email_service.send_password_reset_email(user.email, reset_link)
    except Exception as exc:  # pragma: no cover - defensive email transport path
        logger.exception(
            "Password reset email dispatch failed for user_id=%s: %s",
            user.id,
            exc,
        )

    audit_repository.log(
        db,
        user_id=user.id,
        action="PASSWORD_RESET_REQUESTED",
        details=f"user_id={user.id}",
    )
    return GENERIC_FORGOT_PASSWORD_MESSAGE


def reset_password_confirm(db: Session, payload: PasswordResetConfirmRequest) -> dict:
    now = _utcnow()
    token_hash = security.hash_password_reset_token(payload.token)
    token_row = password_reset_repository.get_valid_by_hash(
        db, token_hash=token_hash, now=now
    )

    if not token_row or not security.verify_password_reset_token(
        payload.token, token_row.token_hash
    ):
        raise HTTPException(status_code=400, detail=SAFE_INVALID_RESET_TOKEN_MESSAGE)

    user = token_row.user
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Account is deactivated")
    if not user.email_verified:
        raise HTTPException(status_code=400, detail=SAFE_INVALID_RESET_TOKEN_MESSAGE)

    _validate_password(payload.new_password)
    user_repository.update(
        db,
        user,
        hashed_password=security.get_password_hash(payload.new_password),
        session_version=user.session_version + 1,
    )
    # Invalidate ALL active reset tokens for this user so that unused
    # tokens from earlier requests cannot be replayed after the password
    # has already been changed.
    password_reset_repository.invalidate_active_for_user(db, user_id=user.id, now=now)
    password_reset_repository.mark_as_used(db, token_row, used_at=now)
    audit_repository.log(
        db,
        user_id=user.id,
        action="PASSWORD_RESET_COMPLETED",
        details=f"user_id={user.id}",
    )
    cache.delete_sync(
        cache_keys.user_profile(user.id),
        user_id=user.id,
        resource="user_profile",
    )
    return GENERIC_RESET_SUCCESS_MESSAGE


def logout(db: Session, user: User) -> dict:
    user_repository.update(db, user, session_version=user.session_version + 1)
    audit_repository.log(
        db, user_id=user.id, action="LOGOUT", details=f"user_id={user.id}"
    )
    return {"message": "Logged out successfully"}


def get_verification_status(user: User) -> dict:
    return {
        "email": user.email,
        "email_verified": user.email_verified,
        "email_verified_at": user.email_verified_at,
    }


def update_profile(db: Session, user: User, payload: ProfileUpdate) -> User:
    fields: dict = {}

    if payload.full_name is not None:
        fields["full_name"] = payload.full_name
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty

    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(
                status_code=400,
                detail="current_password is required to set a new password",
            )
        if not security.verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        _validate_password(payload.new_password)
        fields["hashed_password"] = security.get_password_hash(payload.new_password)
        fields["session_version"] = user.session_version + 1

    user = user_repository.update(db, user, **fields)
    audit_repository.log(
        db, user_id=user.id, action="UPDATE_PROFILE", details=f"user_id={user.id}"
    )
    cache.delete_sync(
        cache_keys.user_profile(user.id), user_id=user.id, resource="user_profile"
    )
    return user


def refresh(user: User) -> AuthResponse:
    return _make_auth_response(user)

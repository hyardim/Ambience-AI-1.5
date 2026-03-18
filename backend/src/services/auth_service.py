import re
from datetime import datetime, timedelta
from collections import defaultdict
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core import security
from src.core.config import settings
from src.db.models import User, UserRole
from src.repositories import audit_repository, password_reset_repository, user_repository
from src.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    PasswordResetConfirmRequest,
    ProfileUpdate,
    UserOut,
    UserRegister,
)
from src.services import email_service
from src.utils.cache import cache, cache_keys


GENERIC_FORGOT_PASSWORD_MESSAGE = {
    "message": "If that email is registered, a password reset link will be sent shortly"
}
GENERIC_RESET_SUCCESS_MESSAGE = {"message": "Password reset successful"}
SAFE_INVALID_RESET_TOKEN_MESSAGE = "Invalid or expired reset token"

_forgot_password_attempts: dict[str, list[datetime]] = defaultdict(list)


def _is_forgot_password_rate_limited(email: str) -> bool:
    now = datetime.utcnow()
    window_start = now - timedelta(seconds=settings.FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS)
    bucket = _forgot_password_attempts[email.lower()]
    bucket[:] = [stamp for stamp in bucket if stamp >= window_start]
    if len(bucket) >= settings.FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS:
        return True
    bucket.append(now)
    return False


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
            status_code=400, detail=f"Password must contain: {', '.join(errors)}")


def _make_auth_response(user: User) -> AuthResponse:
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token(
        data={"sub": user.email, "role": user.role.value},
        expires_delta=expires,
    )
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


def login(db: Session, email: str, password: str) -> AuthResponse:
    user = user_repository.get_by_email(db, email)
    if not user or not security.verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit_repository.log(db, user_id=user.id, action="LOGIN",
                         details=f"user_id={user.id}")
    return _make_auth_response(user)


def register(db: Session, payload: UserRegister) -> AuthResponse:
    if user_repository.get_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        role = UserRole(payload.role)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Invalid role: {payload.role}")

    if role == UserRole.SPECIALIST and not payload.specialty:
        raise HTTPException(
            status_code=400, detail="Specialists must provide a specialty")

    _validate_password(payload.password)

    user = user_repository.create(
        db,
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=payload.full_name,
        role=role,
        specialty=payload.specialty,
    )
    audit_repository.log(db, user_id=user.id,
                         action="REGISTER", details=f"user_id={user.id}")
    return _make_auth_response(user)


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

    now = datetime.utcnow()
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
    except Exception:
        # Keep response generic to avoid account existence disclosure.
        pass

    audit_repository.log(
        db,
        user_id=user.id,
        action="PASSWORD_RESET_REQUESTED",
        details=f"user_id={user.id}",
    )
    return GENERIC_FORGOT_PASSWORD_MESSAGE


def reset_password_confirm(db: Session, payload: PasswordResetConfirmRequest) -> dict:
    now = datetime.utcnow()
    token_hash = security.hash_password_reset_token(payload.token)
    token_row = password_reset_repository.get_valid_by_hash(db, token_hash=token_hash, now=now)

    if not token_row or not security.verify_password_reset_token(payload.token, token_row.token_hash):
        raise HTTPException(status_code=400, detail=SAFE_INVALID_RESET_TOKEN_MESSAGE)

    user = token_row.user
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Account is deactivated")

    _validate_password(payload.new_password)
    user_repository.update(db, user, hashed_password=security.get_password_hash(payload.new_password))
    password_reset_repository.mark_as_used(db, token_row, used_at=now)
    audit_repository.log(db, user_id=user.id, action="PASSWORD_RESET_COMPLETED", details=f"user_id={user.id}")
    cache.delete_sync(cache_keys.user_profile(user.id), user_id=user.id, resource="user_profile")
    return GENERIC_RESET_SUCCESS_MESSAGE


def logout(db: Session, user: User) -> dict:
    audit_repository.log(db, user_id=user.id, action="LOGOUT",
                         details=f"user_id={user.id}")
    return {"message": "Logged out successfully"}


def update_profile(db: Session, user: User, payload: ProfileUpdate) -> User:
    fields: dict = {}

    if payload.full_name is not None:
        fields["full_name"] = payload.full_name
    if payload.specialty is not None:
        fields["specialty"] = payload.specialty

    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(
                status_code=400, detail="current_password is required to set a new password"
            )
        if not security.verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(
                status_code=400, detail="Current password is incorrect")
        _validate_password(payload.new_password)
        fields["hashed_password"] = security.get_password_hash(
            payload.new_password)

    user = user_repository.update(db, user, **fields)
    audit_repository.log(db, user_id=user.id,
                         action="UPDATE_PROFILE", details=f"user_id={user.id}")
    cache.delete_sync(cache_keys.user_profile(user.id),
                      user_id=user.id, resource="user_profile")
    return user

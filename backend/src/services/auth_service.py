import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core import security
from src.db.models import User, UserRole
from src.repositories import audit_repository, user_repository
from src.schemas.auth import (
    AuthResponse,
    PasswordResetRequest,
    ProfileUpdate,
    UserOut,
    UserRegister,
)
from src.utils.cache import cache, cache_keys


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


def login(db: Session, email: str, password: str) -> AuthResponse:
    user = user_repository.get_by_email(db, email)
    if not user or not security.verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit_repository.log(
        db, user_id=user.id, action="LOGIN", details=f"user_id={user.id}"
    )
    return _make_auth_response(user)


def register(db: Session, payload: UserRegister) -> AuthResponse:
    if user_repository.get_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        role = UserRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")

    if role == UserRole.SPECIALIST and not payload.specialty:
        raise HTTPException(
            status_code=400, detail="Specialists must provide a specialty"
        )

    _validate_password(payload.password)

    user = user_repository.create(
        db,
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=payload.full_name,
        role=role,
        specialty=payload.specialty,
    )
    audit_repository.log(
        db, user_id=user.id, action="REGISTER", details=f"user_id={user.id}"
    )
    return _make_auth_response(user)


def reset_password(db: Session, payload: PasswordResetRequest) -> dict:
    user = user_repository.get_by_email(db, payload.email)
    if not user:
        # Return generic message to avoid leaking whether the email exists
        return {"message": "If that email is registered, the password has been reset"}
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is deactivated")
    _validate_password(payload.new_password)
    user_repository.update(
        db,
        user,
        hashed_password=security.get_password_hash(payload.new_password),
        session_version=user.session_version + 1,
    )
    audit_repository.log(
        db, user_id=user.id, action="PASSWORD_RESET", details=f"user_id={user.id}"
    )
    cache.delete_sync(
        cache_keys.user_profile(user.id), user_id=user.id, resource="user_profile"
    )
    return {"message": "If that email is registered, the password has been reset"}


def logout(db: Session, user: User) -> dict:
    user_repository.update(db, user, session_version=user.session_version + 1)
    audit_repository.log(
        db, user_id=user.id, action="LOGOUT", details=f"user_id={user.id}"
    )
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

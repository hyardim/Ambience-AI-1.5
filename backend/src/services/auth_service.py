from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core import security
from src.core.config import settings
from src.db.models import User, UserRole
from src.repositories import audit_repository, user_repository
from src.schemas.auth import AuthResponse, ProfileUpdate, UserOut, UserRegister


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
    audit_repository.log(db, user_id=user.id, action="LOGIN", details=user.email)
    return _make_auth_response(user)


def register(db: Session, payload: UserRegister) -> AuthResponse:
    if user_repository.get_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        role = UserRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")

    if role == UserRole.SPECIALIST and not payload.specialty:
        raise HTTPException(status_code=400, detail="Specialists must provide a specialty")

    user = user_repository.create(
        db,
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=payload.full_name,
        role=role,
        specialty=payload.specialty,
    )
    audit_repository.log(db, user_id=user.id, action="REGISTER", details=payload.email)
    return _make_auth_response(user)


def logout(db: Session, user: User) -> dict:
    audit_repository.log(db, user_id=user.id, action="LOGOUT", details=user.email)
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
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        fields["hashed_password"] = security.get_password_hash(payload.new_password)

    user = user_repository.update(db, user, **fields)
    audit_repository.log(db, user_id=user.id, action="UPDATE_PROFILE", details=user.email)
    return user

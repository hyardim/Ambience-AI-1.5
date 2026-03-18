from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.db.models import User
from src.db.session import get_db
from src.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    PasswordResetConfirmRequest,
    ProfileUpdate,
    UserOut,
    UserRegister,
)
from src.services import auth_service

router = APIRouter()


@router.post("/login", response_model=AuthResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    return auth_service.login(db, form_data.username, form_data.password)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return auth_service.register(db, payload)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user_obj)):
    return current_user


@router.post("/logout")
def logout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return auth_service.logout(db, current_user)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    return auth_service.forgot_password(db, payload)


@router.post("/reset-password/confirm")
def reset_password_confirm(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    return auth_service.reset_password_confirm(db, payload)


@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return auth_service.update_profile(db, current_user, payload)

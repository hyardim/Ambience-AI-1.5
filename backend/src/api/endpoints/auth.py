from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_obj
from src.core import security
from src.db.models import User
from src.db.session import get_db
from src.repositories import user_repository
from src.schemas.auth import (
    AuthResponse,
    PasswordResetRequest,
    ProfileUpdate,
    UserOut,
    UserRegister,
)
from src.services import auth_service

router = APIRouter()


@router.post("/login", response_model=AuthResponse)
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    auth = auth_service.login(db, form_data.username, form_data.password)
    user = user_repository.get_by_email(db, auth.user.email)
    if user is None:  # pragma: no cover - defensive
        raise RuntimeError("Authenticated user disappeared during login")
    security.set_auth_cookies(
        response,
        access_token=auth.access_token,
        refresh_token=security.create_refresh_token_for_user(user),
    )
    return auth


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
def register(
    payload: UserRegister,
    response: Response,
    db: Session = Depends(get_db),
):
    auth = auth_service.register(db, payload)
    user = user_repository.get_by_email(db, auth.user.email)
    if user is None:  # pragma: no cover - defensive
        raise RuntimeError("Registered user disappeared before cookie issuance")
    security.set_auth_cookies(
        response,
        access_token=auth.access_token,
        refresh_token=security.create_refresh_token_for_user(user),
    )
    return auth


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user_obj)):
    return current_user


@router.post("/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    result = auth_service.logout(db, current_user)
    security.clear_auth_cookies(response)
    return result


@router.post("/refresh", response_model=AuthResponse)
def refresh_session(
    response: Response,
    current_user: User = Depends(security.get_refresh_user),
):
    auth = auth_service.refresh(current_user)
    security.set_auth_cookies(
        response,
        access_token=auth.access_token,
        refresh_token=security.create_refresh_token_for_user(current_user),
    )
    return auth


@router.post("/reset-password")
def reset_password(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    return auth_service.reset_password(db, payload)


@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_obj),
):
    return auth_service.update_profile(db, current_user, payload)

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Optional, cast

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import User
from src.db.session import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> User | bool:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return False
    typed_user = cast(User, user)
    if not verify_password(password, str(typed_user.hashed_password)):
        return False
    return typed_user


def _encode_token(
    data: dict[str, Any],
    *,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "type": token_type})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(
    data: dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    return _encode_token(
        data,
        token_type="access",
        expires_delta=expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    data: dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    return _encode_token(
        data,
        token_type="refresh",
        expires_delta=expires_delta
        or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_access_token_for_user(user: User) -> str:
    return create_access_token(
        {
            "sub": user.email,
            "role": user.role.value,
            "sv": user.session_version,
        }
    )


def create_refresh_token_for_user(user: User) -> str:
    return create_refresh_token(
        {
            "sub": user.email,
            "role": user.role.value,
            "sv": user.session_version,
        }
    )


def generate_password_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password_reset_token(token: str) -> str:
    pepper = settings.PASSWORD_RESET_TOKEN_PEPPER or settings.SECRET_KEY
    payload = f"{pepper}:{token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_password_reset_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_password_reset_token(token), token_hash)


def generate_email_verification_token() -> str:
    return secrets.token_urlsafe(32)


def hash_email_verification_token(token: str) -> str:
    pepper = settings.EMAIL_VERIFICATION_TOKEN_PEPPER or settings.SECRET_KEY
    payload = f"{pepper}:{token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_email_verification_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_email_verification_token(token), token_hash)


def _decode_token_payload(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def decode_token(token: str) -> str:
    try:
        payload = _decode_token_payload(token)
    except JWTError as exc:
        raise _credentials_exception() from exc
    if payload.get("type") != "access":
        raise _credentials_exception()
    email = payload.get("sub")
    if not isinstance(email, str):
        raise _credentials_exception()
    return email


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _get_request_token(request: Request, bearer_token: str | None) -> str | None:
    if bearer_token:
        return bearer_token
    cookie_token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None


def _get_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


def _validate_payload(
    payload: dict[str, Any],
    *,
    expected_type: str,
) -> tuple[str, int | None]:
    if payload.get("type") != expected_type:
        raise _credentials_exception()
    email = payload.get("sub")
    if not isinstance(email, str):
        raise _credentials_exception()
    session_version = payload.get("sv")
    if session_version is not None and not isinstance(session_version, int):
        raise _credentials_exception()
    return email, session_version


def _resolve_user_from_token(
    db: Session,
    token: str,
    *,
    expected_type: str,
) -> User:
    try:
        payload = _decode_token_payload(token)
        email, session_version = _validate_payload(payload, expected_type=expected_type)
    except JWTError as exc:
        raise _credentials_exception() from exc

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise _credentials_exception()
    if session_version is not None and user.session_version != session_version:
        raise _credentials_exception()
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str | None = Depends(oauth2_scheme),
) -> str:
    token = _get_request_token(request, bearer_token)
    if not token:
        raise _credentials_exception()
    user = _resolve_user_from_token(db, token, expected_type="access")
    return cast(str, user.email)


def get_current_user_from_cookie_or_header(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str | None = Depends(oauth2_scheme),
) -> User:
    token = _get_request_token(request, bearer_token)
    if not token:
        raise _credentials_exception()
    return _resolve_user_from_token(db, token, expected_type="access")


def get_refresh_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _get_refresh_cookie(request)
    if not token:
        raise _credentials_exception()
    return _resolve_user_from_token(db, token, expected_type="refresh")


def get_user_from_access_token(db: Session, token: str) -> User:
    return _resolve_user_from_token(db, token, expected_type="access")


def set_auth_cookies(response: Response, *, access_token: str, refresh_token: str) -> None:
    cookie_common: dict[str, Any] = {
        "httponly": True,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "domain": settings.COOKIE_DOMAIN,
        "path": "/",
    }
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **cookie_common,
    )
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **cookie_common,
    )


def clear_auth_cookies(response: Response) -> None:
    cookie_common: dict[str, Any] = {
        "domain": settings.COOKIE_DOMAIN,
        "path": "/",
    }
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, **cookie_common)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, **cookie_common)

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from urllib.parse import urlparse

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
_SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_UNSAFE_BEARER_EXEMPT_PATH_PREFIXES = (
    "/auth/login",
    "/auth/register",
    "/auth/logout",
    "/auth/refresh",
    "/auth/forgot-password",
    "/auth/reset-password/confirm",
    "/auth/resend-verification",
    "/auth/verify-email/confirm",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password/confirm",
    "/api/v1/auth/resend-verification",
    "/api/v1/auth/verify-email/confirm",
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash.

    Args:
        plain_password: The plain-text password to check.
        hashed_password: The stored bcrypt hash.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plain-text password using bcrypt.

    Args:
        password: The plain-text password to hash.

    Returns:
        The bcrypt hash string.
    """
    return pwd_context.hash(password)


def authenticate_user(db: Session, email: str, password: str) -> User | bool:
    """Look up a user by email and verify their password.

    Args:
        db: Database session.
        email: The user's email address.
        password: The plain-text password to verify.

    Returns:
        The User object on success, or False if credentials are invalid.
    """
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
    """Create a signed JWT access token.

    Args:
        data: Claims to embed in the token (must include ``sub``).
        expires_delta: Custom expiration duration; defaults to config value.

    Returns:
        The encoded JWT string.
    """
    return _encode_token(
        data,
        token_type="access",
        expires_delta=expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    data: dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Create a signed JWT refresh token.

    Args:
        data: Claims to embed in the token (must include ``sub``).
        expires_delta: Custom expiration duration; defaults to config value.

    Returns:
        The encoded JWT string.
    """
    return _encode_token(
        data,
        token_type="refresh",
        expires_delta=expires_delta
        or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_access_token_for_user(user: User) -> str:
    """Create an access token pre-populated with the user's claims.

    Args:
        user: The authenticated user.

    Returns:
        The encoded JWT access token string.
    """
    return create_access_token(
        {
            "sub": user.email,
            "role": user.role.value,
            "sv": user.session_version,
        }
    )


def create_refresh_token_for_user(user: User) -> str:
    """Create a refresh token pre-populated with the user's claims.

    Args:
        user: The authenticated user.

    Returns:
        The encoded JWT refresh token string.
    """
    return create_refresh_token(
        {
            "sub": user.email,
            "role": user.role.value,
            "sv": user.session_version,
        }
    )


def generate_secure_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(token: str, pepper: str) -> str:
    payload = f"{pepper}:{token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_token(token: str, token_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(_hash_token(token, pepper), token_hash)


# Password-reset token helpers (delegate to shared core)
generate_password_reset_token = generate_secure_token


def hash_password_reset_token(token: str) -> str:
    return _hash_token(
        token, settings.PASSWORD_RESET_TOKEN_PEPPER or settings.SECRET_KEY
    )


def verify_password_reset_token(token: str, token_hash: str) -> bool:
    return _verify_token(
        token, token_hash, settings.PASSWORD_RESET_TOKEN_PEPPER or settings.SECRET_KEY
    )


# Email-verification token helpers (delegate to shared core)
generate_email_verification_token = generate_secure_token


def hash_email_verification_token(token: str) -> str:
    return _hash_token(
        token, settings.EMAIL_VERIFICATION_TOKEN_PEPPER or settings.SECRET_KEY
    )


def verify_email_verification_token(token: str, token_hash: str) -> bool:
    return _verify_token(
        token,
        token_hash,
        settings.EMAIL_VERIFICATION_TOKEN_PEPPER or settings.SECRET_KEY,
    )


def _decode_token_payload(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def decode_token(token: str) -> str:
    """Decode a JWT access token and return the subject email.

    Args:
        token: The encoded JWT string.

    Returns:
        The email address from the token's ``sub`` claim.

    Raises:
        HTTPException: If the token is invalid, expired, or not an access token.
    """
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


def _request_path(request: Request) -> str:
    url = getattr(request, "url", None)
    path = getattr(url, "path", None)
    if isinstance(path, str):
        return path
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        scope_path = scope.get("path")
        if isinstance(scope_path, str):
            return scope_path
    return ""


def _enforce_bearer_header_for_unsafe_cookie_auth(
    request: Request,
    bearer_token: str | None,
) -> None:
    """Reject unsafe cookie-only requests to mitigate CSRF-style form submissions."""
    method = str(getattr(request, "method", "GET")).upper()
    if method in _SAFE_HTTP_METHODS:
        return

    path = _request_path(request)
    if (
        not bearer_token
        and request.cookies.get(settings.ACCESS_COOKIE_NAME)
        and (
            path.startswith("/auth/logout")
            or path.startswith("/api/v1/auth/logout")
        )
    ):
        _enforce_cookie_request_origin(request)

    if any(path.startswith(prefix) for prefix in _UNSAFE_BEARER_EXEMPT_PATH_PREFIXES):
        return

    if bearer_token:
        return

    if request.cookies.get(settings.ACCESS_COOKIE_NAME):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="State-changing requests must include a bearer token",
        )


def _get_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


def _is_allowed_origin(origin_or_referer: str) -> bool:
    if not origin_or_referer:
        return False
    parsed = urlparse(origin_or_referer)
    if not parsed.scheme or not parsed.netloc:
        return False
    normalized = f"{parsed.scheme}://{parsed.netloc}".lower()
    allowed = {origin.strip().lower() for origin in settings.ALLOWED_ORIGINS}
    return normalized in allowed


def _enforce_cookie_request_origin(request: Request) -> None:
    """Require same-origin semantics for cookie-auth unsafe requests when headers are present."""
    headers = getattr(request, "headers", {})
    origin = headers.get("origin") if hasattr(headers, "get") else None
    referer = headers.get("referer") if hasattr(headers, "get") else None

    # For non-browser clients where these headers are typically absent, keep
    # backward-compatible behavior.
    if not origin and not referer:
        return

    if origin and _is_allowed_origin(origin):
        return
    if referer and _is_allowed_origin(referer):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Refresh request origin is not allowed",
    )


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
    """Decode a JWT, look up the user, and verify active status and session version."""
    try:
        payload = _decode_token_payload(token)
        email, session_version = _validate_payload(payload, expected_type=expected_type)
    except JWTError as exc:
        raise _credentials_exception() from exc

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise _credentials_exception()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )
    if session_version is not None and user.session_version != session_version:
        raise _credentials_exception()
    return user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str | None = Depends(oauth2_scheme),
) -> str:
    """FastAPI dependency that extracts and returns the current user's email.

    Reads the JWT from the Authorization header or the access cookie.

    Raises:
        HTTPException: If no valid token is present or the user is inactive.
    """
    _enforce_bearer_header_for_unsafe_cookie_auth(request, bearer_token)
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
    """FastAPI dependency that returns the full User model for the current session.

    Reads the JWT from the Authorization header or the access cookie.

    Raises:
        HTTPException: If no valid token is present or the user is inactive.
    """
    _enforce_bearer_header_for_unsafe_cookie_auth(request, bearer_token)
    token = _get_request_token(request, bearer_token)
    if not token:
        raise _credentials_exception()
    return _resolve_user_from_token(db, token, expected_type="access")


def get_refresh_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency that resolves a user from the refresh-token cookie.

    Raises:
        HTTPException: If no refresh cookie is present or the token is invalid.
    """
    _enforce_cookie_request_origin(request)
    token = _get_refresh_cookie(request)
    if not token:
        raise _credentials_exception()
    return _resolve_user_from_token(db, token, expected_type="refresh")


def get_user_from_access_token(db: Session, token: str) -> User:
    """Resolve a User from a raw access-token string.

    Args:
        db: Database session.
        token: The encoded JWT access token.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException: If the token is invalid or the user is inactive.
    """
    return _resolve_user_from_token(db, token, expected_type="access")


def set_auth_cookies(
    response: Response, *, access_token: str, refresh_token: str
) -> None:
    """Set HTTP-only access and refresh token cookies on the response.

    Args:
        response: The outgoing HTTP response.
        access_token: The JWT access token value.
        refresh_token: The JWT refresh token value.
    """
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
    """Remove access and refresh token cookies from the response.

    Args:
        response: The outgoing HTTP response.
    """
    cookie_common: dict[str, Any] = {
        "domain": settings.COOKIE_DOMAIN,
        "path": "/",
    }
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, **cookie_common)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, **cookie_common)

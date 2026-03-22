import logging
import os
import warnings
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_KEY = "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD"
_INSECURE_RAG_INTERNAL_DEFAULT = "dev-rag-internal-key"
_DEMO_SEED_ALLOWED_ENVS = {"development", "test"}
_PLACEHOLDER_MARKERS = ("change_me", "example", "test_secret")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Ambience AI"
    PROJECT_VERSION: str = "1.5.0"

    SECRET_KEY: str = _INSECURE_DEFAULT_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = (
        "postgresql://admin:CHANGE_ME_DB_PASSWORD@db_vector:5432/ambience_knowledge"
    )
    RAG_SERVICE_URL: str = "http://rag_service:8001"
    RAG_INTERNAL_API_KEY: str = ""
    RAG_REQUEST_TIMEOUT_SECONDS: float = 120.0
    UPLOAD_DIR: str = "/app/uploads"
    APP_ENV: Literal["development", "test", "production"] = "development"
    AUTH_BOOTSTRAP_DEMO_USERS: bool = False
    DEMO_GP_PASSWORD: str = ""
    DEMO_SPECIALIST_PASSWORD: str = ""
    DEMO_ADMIN_PASSWORD: str = ""

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: list[str] = [
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
    ]

    # Session cookies
    ACCESS_COOKIE_NAME: str = "ambience_access_token"
    REFRESH_COOKIE_NAME: str = "ambience_refresh_token"
    COOKIE_SAMESITE: str = "lax"
    COOKIE_SECURE: bool = True
    COOKIE_DOMAIN: str | None = None

    # File upload limits
    MAX_FILE_SIZE_BYTES: int = 3 * 1024 * 1024
    MAX_FILES_PER_CHAT: int = 5
    FILE_CONTEXT_CHAR_LIMIT: int = 8_000
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = [
        ".pdf",
        ".txt",
        ".md",
        ".rtf",
        ".doc",
        ".docx",
        ".csv",
        ".json",
        ".xml",
    ]

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    INLINE_AI_TASKS: bool = False

    # Cache
    CACHE_ENABLED: bool = True
    REDIS_URL: str = "redis://redis:6379/0"
    CACHE_KEY_PREFIX: str = "cache"
    CACHE_CHAT_LIST_TTL: int = 30
    CACHE_CHAT_DETAIL_TTL: int = 60
    CACHE_PROFILE_TTL: int = 300
    CACHE_SPECIALIST_LIST_TTL: int = 30
    CACHE_ADMIN_STATS_TTL: int = 30
    CACHE_ADMIN_CHAT_TTL: int = 30
    CACHE_ADMIN_AUDIT_LOG_TTL: int = 15
    CACHE_NOTIFICATION_TTL: int = 30

    # RAG / chat flow tuning
    CHAT_RAG_TOP_K: int = 4
    CHAT_HISTORY_MESSAGE_LIMIT: int = 8

    # Auth verification / recovery
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = 30
    PASSWORD_RESET_TOKEN_PEPPER: str = ""
    EMAIL_VERIFICATION_TOKEN_TTL_MINUTES: int = 60
    EMAIL_VERIFICATION_TOKEN_PEPPER: str = ""
    NEW_USERS_REQUIRE_EMAIL_VERIFICATION: bool = True
    ALLOW_LEGACY_UNVERIFIED_LOGIN: bool = False
    FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS: int = 900
    FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    RESEND_VERIFICATION_RATE_LIMIT_WINDOW_SECONDS: int = 900
    RESEND_VERIFICATION_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True
    PASSWORD_RESET_EMAIL_LOG_ONLY: bool = True
    EMAIL_VERIFICATION_EMAIL_LOG_ONLY: bool = True


settings = Settings()


def _is_production_env() -> bool:
    return settings.APP_ENV == "production"


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def validate_settings() -> None:
    """Emit warnings for insecure defaults at startup."""
    logger = logging.getLogger("backend.config")
    if settings.SECRET_KEY == _INSECURE_DEFAULT_KEY:
        if _is_production_env():
            logger.error(
                "SECRET_KEY is using the insecure default and cannot be used in production"
            )
            raise RuntimeError(
                "Invalid configuration: set SECRET_KEY to a strong non-default value"
            )
        warnings.warn(
            "SECRET_KEY is using the insecure default value. "
            "Set a strong SECRET_KEY via environment variable before deploying.",
            stacklevel=1,
        )
        logger.warning(
            "SECRET_KEY is using the insecure default — do NOT deploy to production"
        )

    if _is_production_env() and settings.AUTH_BOOTSTRAP_DEMO_USERS:
        logger.error(
            "AUTH_BOOTSTRAP_DEMO_USERS cannot be enabled when APP_ENV=production"
        )
        raise RuntimeError(
            "Invalid configuration: disable AUTH_BOOTSTRAP_DEMO_USERS in production"
        )

    if _is_production_env():
        insecure_fields = {
            "DATABASE_URL": settings.DATABASE_URL,
            "EMAIL_VERIFICATION_TOKEN_PEPPER": settings.EMAIL_VERIFICATION_TOKEN_PEPPER,
            "PASSWORD_RESET_TOKEN_PEPPER": settings.PASSWORD_RESET_TOKEN_PEPPER,
        }
        bad_fields = [
            name
            for name, value in insecure_fields.items()
            if _looks_like_placeholder(value)
        ]
        if bad_fields:
            raise RuntimeError(
                "Invalid configuration: set strong non-placeholder values for "
                + ", ".join(bad_fields)
            )

    if _is_production_env():
        origins = [origin.strip().lower() for origin in settings.ALLOWED_ORIGINS]
        if not origins:
            raise RuntimeError(
                "Invalid configuration: ALLOWED_ORIGINS must be set in production"
            )
        if any(origin == "*" for origin in origins):
            raise RuntimeError(
                "Invalid configuration: wildcard CORS origins are not allowed in production"
            )
        if any(
            "localhost" in origin or "127.0.0.1" in origin or "0.0.0.0" in origin
            for origin in origins
        ):
            raise RuntimeError(
                "Invalid configuration: localhost CORS origins are not allowed in production"
            )
        if any(method == "*" for method in settings.CORS_ALLOW_METHODS):
            raise RuntimeError(
                "Invalid configuration: wildcard CORS methods are not allowed in production"
            )
        if any(header == "*" for header in settings.CORS_ALLOW_HEADERS):
            raise RuntimeError(
                "Invalid configuration: wildcard CORS headers are not allowed in production"
            )

    if (
        settings.AUTH_BOOTSTRAP_DEMO_USERS
        and settings.APP_ENV in _DEMO_SEED_ALLOWED_ENVS
    ):
        missing = [
            name
            for name, value in (
                ("DEMO_GP_PASSWORD", settings.DEMO_GP_PASSWORD),
                ("DEMO_SPECIALIST_PASSWORD", settings.DEMO_SPECIALIST_PASSWORD),
                ("DEMO_ADMIN_PASSWORD", settings.DEMO_ADMIN_PASSWORD),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Invalid configuration: set demo seed passwords when "
                "AUTH_BOOTSTRAP_DEMO_USERS is enabled. Missing: " + ", ".join(missing)
            )

    if _is_production_env():
        rag_key = settings.RAG_INTERNAL_API_KEY.strip()
        if not rag_key or rag_key == _INSECURE_RAG_INTERNAL_DEFAULT:
            raise RuntimeError(
                "Invalid configuration: set RAG_INTERNAL_API_KEY to a strong "
                "non-default value in production"
            )

    if _is_production_env():
        smtp_host = settings.SMTP_HOST.strip()
        smtp_from = settings.SMTP_FROM.strip()
        smtp_user = settings.SMTP_USERNAME.strip()
        smtp_password = settings.SMTP_PASSWORD.strip()

        # Password reset and verification flows can be configured to use real SMTP.
        # Validate required transport fields up-front to avoid silent delivery failures.
        email_delivery_required = not settings.PASSWORD_RESET_EMAIL_LOG_ONLY or (
            settings.NEW_USERS_REQUIRE_EMAIL_VERIFICATION
            and not settings.EMAIL_VERIFICATION_EMAIL_LOG_ONLY
        )
        if email_delivery_required and (not smtp_host or not smtp_from):
            raise RuntimeError(
                "Invalid configuration: SMTP_HOST and SMTP_FROM must be set in "
                "production when email delivery is enabled"
            )
        if smtp_user and not smtp_password:
            raise RuntimeError(
                "Invalid configuration: SMTP_PASSWORD must be set when "
                "SMTP_USERNAME is provided"
            )

    # SSE uses an in-process event bus. Fail fast if multi-worker server
    # settings are configured to avoid silent stream delivery gaps.
    worker_count = os.getenv("WEB_CONCURRENCY") or os.getenv("UVICORN_WORKERS")
    if worker_count:
        try:
            parsed_workers = int(worker_count)
        except ValueError as exc:
            raise RuntimeError(
                "Invalid configuration: WEB_CONCURRENCY/UVICORN_WORKERS must be an integer"
            ) from exc
        if parsed_workers > 1:
            raise RuntimeError(
                "Invalid configuration: SSE requires a single backend worker with "
                "the current in-process event bus"
            )

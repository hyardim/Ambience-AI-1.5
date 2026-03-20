import logging
import warnings
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_KEY = "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD"


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
    RAG_REQUEST_TIMEOUT_SECONDS: float = 120.0
    UPLOAD_DIR: str = "/app/uploads"
    APP_ENV: Literal["development", "test", "production"] = "development"
    AUTH_BOOTSTRAP_DEMO_USERS: bool = False

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

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


def validate_settings() -> None:
    """Emit warnings for insecure defaults at startup."""
    logger = logging.getLogger("backend.config")
    if settings.SECRET_KEY == _INSECURE_DEFAULT_KEY:
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

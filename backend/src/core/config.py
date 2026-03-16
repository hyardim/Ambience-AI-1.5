import logging
import warnings
from pathlib import Path

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
        "postgresql://admin:team20_password@db_vector:5432/ambience_knowledge"
    )
    RAG_SERVICE_URL: str = "http://rag_service:8001"
    RAG_REQUEST_TIMEOUT_SECONDS: float = 120.0
    UPLOAD_DIR: str = "/app/uploads"
    AUTH_BOOTSTRAP_DEMO_USERS: bool = True

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Session cookies
    ACCESS_COOKIE_NAME: str = "ambience_access_token"
    REFRESH_COOKIE_NAME: str = "ambience_refresh_token"
    COOKIE_SAMESITE: str = "lax"
    COOKIE_SECURE: bool = True
    COOKIE_DOMAIN: str | None = None

    # File upload limits
    MAX_FILE_SIZE_BYTES: int = 3 * 1024 * 1024  # 3 MB per file
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


settings = Settings()


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

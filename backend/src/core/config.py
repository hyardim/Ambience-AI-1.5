from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Ambience AI"
    PROJECT_VERSION: str = "1.5.0"

    SECRET_KEY: str = "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    DATABASE_URL: str = (
        "postgresql://admin:team20_password@db_vector:5432/ambience_knowledge"
    )
    RAG_SERVICE_URL: str = "http://rag_service:8001"
    RAG_REQUEST_TIMEOUT_SECONDS: float = 120.0
    UPLOAD_DIR: str = "/app/uploads"
    AUTH_BOOTSTRAP_DEMO_USERS: bool = True

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


settings = Settings()

import os


def _get_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    PROJECT_NAME: str = "Ambience AI"
    PROJECT_VERSION: str = "1.5.0"

    # Security
    # In production, we would pull this from os.getenv("SECRET_KEY")
    SECRET_KEY: str = "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    # Cache
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CACHE_KEY_PREFIX: str = os.getenv("CACHE_KEY_PREFIX", "cache")
    CACHE_CHAT_LIST_TTL: int = int(os.getenv("CACHE_CHAT_LIST_TTL", "30"))
    CACHE_CHAT_DETAIL_TTL: int = int(os.getenv("CACHE_CHAT_DETAIL_TTL", "60"))
    CACHE_PROFILE_TTL: int = int(os.getenv("CACHE_PROFILE_TTL", "300"))

    FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
    PASSWORD_RESET_TOKEN_TTL_MINUTES: int = int(
        os.getenv("PASSWORD_RESET_TOKEN_TTL_MINUTES", "30")
    )
    PASSWORD_RESET_TOKEN_PEPPER: str = os.getenv("PASSWORD_RESET_TOKEN_PEPPER", SECRET_KEY)

    FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS: int = int(
        os.getenv("FORGOT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS", "900")
    )
    FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS: int = int(
        os.getenv("FORGOT_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS", "5")
    )

    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")
    SMTP_USE_TLS: bool = _get_bool("SMTP_USE_TLS", True)
    PASSWORD_RESET_EMAIL_LOG_ONLY: bool = _get_bool("PASSWORD_RESET_EMAIL_LOG_ONLY", True)


settings = Settings()

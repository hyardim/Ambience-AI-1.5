import os


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


settings = Settings()

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

COMMON_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=PROJECT_ROOT / ".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
)


class AppBaseSettings(BaseSettings):
    model_config = COMMON_SETTINGS_CONFIG

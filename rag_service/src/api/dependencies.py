import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import Field

from src.config import (
    DATABASE_URL,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    AppBaseSettings,
)


class Settings(AppBaseSettings):
    database_url: str = Field(default=os.getenv("DATABASE_URL", DATABASE_URL))
    llm_base_url: str = Field(default=LLM_BASE_URL)
    llm_model: str = Field(default=LLM_MODEL)
    llm_api_key: str = Field(default=LLM_API_KEY)
    llm_max_tokens: int = Field(default=LLM_MAX_TOKENS)
    llm_temperature: float = Field(default=LLM_TEMPERATURE)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_db_url(settings: Annotated[Settings, Depends(get_settings)]) -> str:
    return settings.database_url

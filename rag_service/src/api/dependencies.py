from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import Field

from src.config import AppBaseSettings, db_config, llm_config


class Settings(AppBaseSettings):
    database_url: str = Field(default=db_config.database_url)
    llm_base_url: str = Field(default=llm_config.llm_base_url)
    llm_model: str = Field(default=llm_config.llm_model)
    llm_api_key: str = Field(default=llm_config.llm_api_key)
    llm_max_tokens: int = Field(default=llm_config.llm_max_tokens)
    llm_temperature: float = Field(default=llm_config.llm_temperature)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_db_url(settings: Annotated[Settings, Depends(get_settings)]) -> str:
    return settings.database_url

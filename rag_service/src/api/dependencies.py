from typing import Annotated

from fastapi import Depends

from src.config import db_config


def get_db_url() -> str:
    return db_config.database_url


DbUrl = Annotated[str, Depends(get_db_url)]

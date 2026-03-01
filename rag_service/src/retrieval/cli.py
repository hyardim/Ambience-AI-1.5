from __future__ import annotations

import os
import sys

import click
from dotenv import load_dotenv

from ..utils.logger import setup_logger
from .citation import format_citation
from .query import RetrievalError
from .retrieve import retrieve

logger = setup_logger(__name__)

_SEPARATOR = "─" * 49

def _resolve_db_url(db_url: str | None) -> str | None:
    if db_url:
        return db_url
    if url := os.environ.get("DATABASE_URL"):
        return url
    load_dotenv()
    return os.environ.get("DATABASE_URL")


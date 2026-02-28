from __future__ import annotations

import time
from typing import Any

import psycopg2
import psycopg2.extras
from pydantic import BaseModel

from ..utils.logger import setup_logger
from .query import RetrievalError

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Pydantic model
# -----------------------------------------------------------------------


class KeywordSearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    rank: float
    metadata: dict[str, Any]

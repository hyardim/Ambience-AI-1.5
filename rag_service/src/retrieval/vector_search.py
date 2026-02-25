from __future__ import annotations

import time
from typing import Any

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from pydantic import BaseModel

from .query import RetrievalError
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Pydantic model
# -----------------------------------------------------------------------


class VectorSearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float
    metadata: dict[str, Any]

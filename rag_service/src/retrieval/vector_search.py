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

# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def vector_search(
    query_embedding: list[float],
    db_url: str,
    top_k: int = 20,
    specialty: str | None = None,
    source_name: str | None = None,
    doc_type: str | None = None,
) -> list[VectorSearchResult]:
    """
    Retrieve top-k most similar chunks via pgvector cosine similarity.

    Args:
        query_embedding: 384-dimensional normalised query vector
        db_url: Postgres connection string
        top_k: Maximum number of results to return
        specialty: Optional metadata filter
        source_name: Optional metadata filter
        doc_type: Optional metadata filter

    Returns:
        List of VectorSearchResult ordered by similarity descending

    Raises:
        RetrievalError: On DB connection failure, missing pgvector extension,
                        or invalid embedding dimensions
    """
    pass
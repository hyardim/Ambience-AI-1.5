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

# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def keyword_search(
    query: str,
    db_url: str,
    top_k: int = 20,
    specialty: str | None = None,
    source_name: str | None = None,
    doc_type: str | None = None,
) -> list[KeywordSearchResult]:
    """
    Retrieve top-k chunks matching the query via PostgreSQL full-text search.

    Uses tsvector/tsquery for exact and stemmed term matching. Complements
    vector search by catching specific drug names, dosages, and medical codes
    that semantic search can miss.

    Args:
        query: Raw natural language query string
        db_url: Postgres connection string
        top_k: Maximum number of results to return
        specialty: Optional metadata filter
        source_name: Optional metadata filter
        doc_type: Optional metadata filter

    Returns:
        List of KeywordSearchResult ordered by ts_rank descending

    Raises:
        RetrievalError: On DB connection failure or missing tsvector column
    """
    pass

# -----------------------------------------------------------------------
# Column check
# -----------------------------------------------------------------------


def _check_tsvector_column(conn: Any) -> None:
    """Raise RetrievalError if text_search_vector column is missing."""
    sql = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'rag_chunks'
        AND column_name = 'text_search_vector';
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    if row is None:
        raise RetrievalError(
            stage="KEYWORD_SEARCH",
            query="",
            message=(
                "text_search_vector column not found on rag_chunks — "
                "run migration 003_add_text_search_vector.sql"
            ),
        )

# -----------------------------------------------------------------------
# Stopword check
# -----------------------------------------------------------------------


def _is_stopword_only_query(conn: Any, query: str) -> bool:
    """Return True if plainto_tsquery produces an empty query (all stopwords)."""
    with conn.cursor() as cur:
        cur.execute("SELECT plainto_tsquery('english', %s)::text", (query,))
        row = cur.fetchone()
    return row is None or row[0] == ""

# -----------------------------------------------------------------------
# Query execution
# -----------------------------------------------------------------------


def _run_query(
    conn: Any,
    query: str,
    top_k: int,
    specialty: str | None,
    source_name: str | None,
    doc_type: str | None,
) -> list[KeywordSearchResult]:
    """Execute the full-text search query and return results."""
    pass
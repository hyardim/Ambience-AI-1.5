from __future__ import annotations

import time
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2 import errors as pg_errors
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
    if not query or not query.strip():
        raise RetrievalError(
            stage="KEYWORD_SEARCH",
            query=query,
            message="Query must not be empty",
        )

    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
        raise RetrievalError(
            stage="KEYWORD_SEARCH",
            query=query,
            message=f"top_k must be a positive integer, got {top_k!r}",
        )

    filters = {
        k: v
        for k, v in {
            "specialty": specialty,
            "source_name": source_name,
            "doc_type": doc_type,
        }.items()
        if v is not None
    }

    logger.debug(f"Running keyword search, top_k={top_k}, filters={filters}")

    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        raise RetrievalError(
            stage="KEYWORD_SEARCH",
            query=query,
            message=f"DB connection failed: {e}",
        ) from e

    try:
        psycopg2.extras.register_default_jsonb(conn)
        results = _run_query(conn, query, top_k, specialty, source_name, doc_type)
    except RetrievalError:
        raise
    except pg_errors.UndefinedColumn as e:
        raise RetrievalError(
            stage="KEYWORD_SEARCH",
            query=query,
            message=(
                "text_search_vector column not found on rag_chunks — "
                "run migration 003_add_text_search_vector.sql"
            ),
        ) from e
    except Exception as e:
        raise RetrievalError(
            stage="KEYWORD_SEARCH",
            query=query,
            message=f"Keyword search failed: {e}",
        ) from e
    finally:
        conn.close()

    return results


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
    if _is_stopword_only_query(conn, query):
        logger.warning("Query consists entirely of stopwords — returning empty results")
        logger.debug("Stopword-only query detected; full text omitted from logs")
        return []

    sql = """
        SELECT
            chunk_id,
            doc_id,
            text,
            ts_rank(text_search_vector, plainto_tsquery('english', %s)) AS rank,
            metadata->>'specialty' AS specialty,
            metadata->>'source_name' AS source_name,
            metadata->>'doc_type' AS doc_type,
            metadata->>'source_url' AS source_url,
            metadata->>'content_type' AS content_type,
            metadata->>'section_title' AS section_title,
            metadata->>'title' AS title,
            (COALESCE(metadata->>'page_start', '0'))::int AS page_start,
            (COALESCE(metadata->>'page_end', '0'))::int AS page_end,
            metadata->'section_path' AS section_path
        FROM rag_chunks
        WHERE
            text_search_vector @@ plainto_tsquery('english', %s)
            AND (%s::text IS NULL OR metadata->>'specialty'   = %s)
            AND (%s::text IS NULL OR metadata->>'source_name' = %s)
            AND (%s::text IS NULL OR metadata->>'doc_type'    = %s)
        ORDER BY rank DESC
        LIMIT %s;
    """

    start = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                query,
                query,
                specialty,
                specialty,
                source_name,
                source_name,
                doc_type,
                doc_type,
                top_k,
            ),
        )
        rows = cur.fetchall()
    elapsed_ms = (time.perf_counter() - start) * 1000

    if not rows:
        logger.debug("Keyword search returned 0 results")
        return []

    results = []
    for row in rows:
        results.append(
            KeywordSearchResult(
                chunk_id=row[0],
                doc_id=row[1],
                text=row[2],
                rank=float(row[3]),
                metadata={
                    "specialty": row[4],
                    "source_name": row[5],
                    "doc_type": row[6],
                    "source_url": row[7],
                    "content_type": row[8],
                    "section_title": row[9],
                    "title": row[10],
                    "page_start": row[11] if row[11] is not None else 0,
                    "page_end": row[12] if row[12] is not None else 0,
                    "section_path": row[13],
                },
            )
        )

    logger.debug(
        f"Keyword search returned {len(results)} results in {elapsed_ms:.0f}ms"
    )
    logger.debug(
        f"Top rank: {results[0].rank:.2f}, bottom rank: {results[-1].rank:.2f}"
    )

    return results

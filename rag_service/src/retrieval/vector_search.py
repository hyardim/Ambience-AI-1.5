from __future__ import annotations

import time
from typing import Any

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from pydantic import BaseModel

from ..utils.logger import setup_logger
from .query import EMBEDDING_DIMENSIONS, RetrievalError

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
        query_embedding: normalised query vector
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
    if len(query_embedding) != EMBEDDING_DIMENSIONS:
        raise RetrievalError(
            stage="VECTOR_SEARCH",
            query="",
            message=(
                f"Invalid embedding dimensions: expected {EMBEDDING_DIMENSIONS}, "
                f"got {len(query_embedding)}"
            ),
        )

    if not isinstance(top_k, int) or top_k <= 0:
        raise RetrievalError(
            stage="VECTOR_SEARCH",
            query="",
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

    logger.debug(f"Running vector search, top_k={top_k}, filters={filters}")

    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        raise RetrievalError(
            stage="VECTOR_SEARCH",
            query="",
            message=f"DB connection failed: {e}",
        ) from e

    try:
        register_vector(conn)
        psycopg2.extras.register_default_jsonb(conn)
        results = _run_query(
            conn, query_embedding, top_k, specialty, source_name, doc_type
        )
    except RetrievalError:
        raise
    except Exception as e:
        raise RetrievalError(
            stage="VECTOR_SEARCH",
            query="",
            message=f"Vector search failed: {e}",
        ) from e
    finally:
        conn.close()

    return results


# -----------------------------------------------------------------------
# Query execution
# -----------------------------------------------------------------------


def _run_query(
    conn: Any,
    query_embedding: list[float],
    top_k: int,
    specialty: str | None,
    source_name: str | None,
    doc_type: str | None,
) -> list[VectorSearchResult]:
    """Execute the vector similarity query and return results."""
    embedding_array = np.array(query_embedding, dtype=np.float32)

    sql = """
        SELECT
            chunk_id,
            doc_id,
            text,
            1 - (embedding <=> %s::vector) AS score,
            metadata->>'specialty'          AS specialty,
            metadata->>'source_name'        AS source_name,
            metadata->>'doc_type'           AS doc_type,
            metadata->>'source_url'         AS source_url,
            metadata->>'content_type'       AS content_type,
            metadata->>'section_title'      AS section_title,
            metadata->>'title'              AS title,
            (metadata->>'page_start')::int  AS page_start,
            (metadata->>'page_end')::int    AS page_end,
            metadata->'section_path'        AS section_path
        FROM rag_chunks
        WHERE
            (%s::text IS NULL OR metadata->>'specialty'   = %s)
            AND (%s::text IS NULL OR metadata->>'source_name' = %s)
            AND (%s::text IS NULL OR metadata->>'doc_type'    = %s)
        ORDER BY embedding <=> %s::vector ASC
        LIMIT %s;
    """

    start = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                embedding_array,
                specialty,
                specialty,
                source_name,
                source_name,
                doc_type,
                doc_type,
                embedding_array,
                top_k,
            ),
        )
        rows = cur.fetchall()
    elapsed_ms = (time.perf_counter() - start) * 1000

    if not rows:
        logger.debug("Vector search returned 0 results")
        return []

    results = []
    for row in rows:
        score = max(float(row[3]), 0.0)
        results.append(
            VectorSearchResult(
                chunk_id=row[0],
                doc_id=row[1],
                text=row[2],
                score=score,
                metadata={
                    "specialty": row[4],
                    "source_name": row[5],
                    "doc_type": row[6],
                    "source_url": row[7],
                    "content_type": row[8],
                    "section_title": row[9],
                    "title": row[10],
                    "page_start": row[11],
                    "page_end": row[12],
                    "section_path": row[13],
                },
            )
        )

    logger.debug(f"Vector search returned {len(results)} results in {elapsed_ms:.0f}ms")
    logger.debug(
        f"Top score: {results[0].score:.2f}, bottom score: {results[-1].score:.2f}"
    )

    return results

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..utils.logger import setup_logger
from .citation import CitedResult, assemble_citations
from .filters import FilterConfig, apply_filters
from .fusion import reciprocal_rank_fusion
from .keyword_search import keyword_search
from .query import RetrievalError, process_query
from .rerank import deduplicate, rerank
from .vector_search import vector_search

logger = setup_logger(__name__)

DEBUG_ARTIFACT_DIR = Path("data/debug/retrieval")

def retrieve(
    query: str,
    db_url: str,
    top_k: int = 5,
    specialty: str | None = None,
    source_name: str | None = None,
    doc_type: str | None = None,
    score_threshold: float = 0.3,
    expand_query: bool = False,
    lambda_param: float = 0.5,
    write_debug_artifacts: bool = False,
) -> list[CitedResult]:
    """
    Run the full retrieval pipeline for a query.

    Stages:
        1. process_query
        2. vector_search
        3. keyword_search
        4. reciprocal_rank_fusion
        5. apply_filters
        6. rerank
        7. deduplicate
        8. assemble_citations

    Args:
        query: Raw user query string
        db_url: PostgreSQL connection string
        top_k: Maximum number of results to return
        specialty: Optional filter by specialty
        source_name: Optional filter by source name
        doc_type: Optional filter by document type
        score_threshold: Minimum RRF score threshold for filtering
        expand_query: Whether to expand query with synonyms
        lambda_param: RRF lambda parameter
        write_debug_artifacts: Write per-stage JSON to data/debug/retrieval/

    Returns:
        List of CitedResult ordered by rerank score descending

    Raises:
        RetrievalError: If a pipeline stage fails unrecoverably
    """
    logger.info(f'Retrieving for query: "{query}", top_k={top_k}')
    total_start = time.perf_counter()

    query_hash = hashlib.md5(query.encode()).hexdigest()[:8]  # noqa: S324
    artifacts: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Stage 1: Query processing
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        processed = process_query(query, expand=expand_query)
    except Exception as e:
        raise RetrievalError(
            stage="QUERY",
            query=query,
            message=str(e),
        ) from e
    logger.debug(f"QUERY complete in {_ms(t)}ms")
    artifacts["01_query"] = processed.model_dump()

    # ------------------------------------------------------------------
    # Stage 2: Vector search
    # ------------------------------------------------------------------
    t = time.perf_counter()
    vector_results = []
    vector_failed = False
    try:
        vector_results = vector_search(
            processed=processed,
            db_url=db_url,
            top_k=top_k * 4,
        )
        logger.debug(f"VECTOR_SEARCH complete in {_ms(t)}ms, {len(vector_results)} results")
    except Exception as e:
        logger.warning(f"VECTOR_SEARCH failed — falling back to keyword only: {e}")
        vector_failed = True
    artifacts["02_vector"] = [_strip_embedding(r.model_dump()) for r in vector_results]

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _strip_embedding(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != "embedding"}


def _maybe_write_artifacts(
    enabled: bool,
    query_hash: str,
    artifacts: dict[str, Any],
) -> None:
    if not enabled:
        return
    out_dir = DEBUG_ARTIFACT_DIR / query_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in artifacts.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
    logger.debug(f"Debug artifacts written to {out_dir}")
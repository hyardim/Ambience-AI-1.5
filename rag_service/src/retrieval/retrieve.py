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
        score_threshold: Minimum score threshold for filtering
        expand_query: Whether to expand query with synonyms
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
    artifacts["01_query"] = processed.model_dump(exclude={"embedding"})

    # ------------------------------------------------------------------
    # Stage 2: Vector search
    # ------------------------------------------------------------------
    t = time.perf_counter()
    vector_results = []
    vector_failed = False
    try:
        vector_results = vector_search(
            query_embedding=processed.embedding,
            db_url=db_url,
            top_k=top_k * 4,
            specialty=specialty,
            source_name=source_name,
            doc_type=doc_type,
        )
        logger.debug(
            f"VECTOR_SEARCH complete in {_ms(t)}ms, {len(vector_results)} results"
        )
    except Exception as e:
        logger.warning(f"VECTOR_SEARCH failed — falling back to keyword only: {e}")
        vector_failed = True
    artifacts["02_vector"] = [r.model_dump() for r in vector_results]

    # ------------------------------------------------------------------
    # Stage 3: Keyword search
    # ------------------------------------------------------------------
    t = time.perf_counter()
    keyword_results = []
    keyword_failed = False
    try:
        keyword_results = keyword_search(
            query=processed.expanded,
            db_url=db_url,
            top_k=top_k * 4,
            specialty=specialty,
            source_name=source_name,
            doc_type=doc_type,
        )
        logger.debug(
            f"KEYWORD_SEARCH complete in {_ms(t)}ms, {len(keyword_results)} results"
        )
    except Exception as e:
        logger.warning(f"KEYWORD_SEARCH failed — falling back to vector only: {e}")
        keyword_failed = True
    artifacts["03_keyword"] = [r.model_dump() for r in keyword_results]

    if vector_failed and keyword_failed:
        raise RetrievalError(
            stage="SEARCH",
            query=query,
            message="Both vector search and keyword search failed.",
        )

    # ------------------------------------------------------------------
    # Stage 4: Fusion
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        fused = reciprocal_rank_fusion(
            vector_results=vector_results,
            keyword_results=keyword_results,
        )
    except Exception as e:
        raise RetrievalError(stage="FUSION", query=query, message=str(e)) from e
    logger.debug(f"FUSION complete in {_ms(t)}ms, {len(fused)} unique chunks")
    artifacts["04_fusion"] = [r.model_dump() for r in fused]

    # ------------------------------------------------------------------
    # Stage 5: Filters
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        config = FilterConfig(
            score_threshold=score_threshold,
            specialty=specialty,
            source_name=source_name,
            doc_type=doc_type,
        )
        filtered = apply_filters(results=fused, config=config)
    except Exception as e:
        raise RetrievalError(stage="FILTERS", query=query, message=str(e)) from e
    logger.debug(f"FILTERS complete in {_ms(t)}ms, {len(filtered)} results remaining")
    artifacts["05_filters"] = [r.model_dump() for r in filtered]

    if not filtered:
        logger.warning(f'No results after filtering for query: "{query}"')
        _maybe_write_artifacts(write_debug_artifacts, query_hash, artifacts)
        return []

    # ------------------------------------------------------------------
    # Stage 6: Rerank
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        reranked = rerank(query=query, results=filtered, top_k=top_k * 2)
    except Exception as e:
        raise RetrievalError(stage="RERANK", query=query, message=str(e)) from e
    logger.debug(f"RERANK complete in {_ms(t)}ms")
    artifacts["06_rerank"] = [r.model_dump() for r in reranked]

    if not reranked:
        logger.warning(f'No results after reranking for query: "{query}"')
        _maybe_write_artifacts(write_debug_artifacts, query_hash, artifacts)
        return []

    # ------------------------------------------------------------------
    # Stage 7: Deduplication
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        deduped = deduplicate(reranked)
    except Exception as e:
        raise RetrievalError(stage="DEDUP", query=query, message=str(e)) from e
    dropped = len(reranked) - len(deduped)
    logger.debug(f"DEDUP complete in {_ms(t)}ms, dropped {dropped}")
    artifacts["07_dedup"] = [r.model_dump() for r in deduped]

    # ------------------------------------------------------------------
    # Stage 8: Citations
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        cited = assemble_citations(deduped[:top_k])
    except Exception as e:
        raise RetrievalError(stage="CITATIONS", query=query, message=str(e)) from e
    logger.debug(f"CITATIONS complete in {_ms(t)}ms")
    artifacts["08_citations"] = [r.model_dump() for r in cited]

    total_ms = _ms(total_start)
    logger.info(f"Retrieval complete in {total_ms}ms, returning {len(cited)} results")

    _maybe_write_artifacts(write_debug_artifacts, query_hash, artifacts)
    return cited


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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

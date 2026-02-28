from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .keyword_search import KeywordSearchResult
from .vector_search import VectorSearchResult

logger = setup_logger(__name__)


# -----------------------------------------------------------------------
# Pydantic model
# -----------------------------------------------------------------------


class FusedResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    rrf_score: float
    vector_score: float | None
    keyword_rank: float | None
    metadata: dict[str, Any]


# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def reciprocal_rank_fusion(
    vector_results: list[VectorSearchResult],
    keyword_results: list[KeywordSearchResult],
    k: int = 60,
    top_k: int = 20,
) -> list[FusedResult]:
    """
    Combine vector and keyword search results using Reciprocal Rank Fusion.

    Combines ranked lists by position rather than score, making it robust
    to incompatible score scales between cosine similarity and ts_rank.

    Args:
        vector_results: Ranked results from vector search
        keyword_results: Ranked results from keyword search
        k: RRF constant — dampens advantage of top ranks (default 60)
        top_k: Maximum number of results to return

    Returns:
        List of FusedResult ordered by RRF score descending

    """
    if not vector_results and not keyword_results:
        return []

    if not vector_results:
        logger.warning("Vector results are empty — fusing keyword results only")
    if not keyword_results:
        logger.warning("Keyword results are empty — fusing vector results only")

    logger.debug(
        f"Fusing {len(vector_results)} vector results + "
        f"{len(keyword_results)} keyword results"
    )

    # Deduplicate each input list by keeping highest-ranked (lowest index) occurrence
    vector_results = _deduplicate(vector_results, list_name="vector")
    keyword_results = _deduplicate(keyword_results, list_name="keyword")

    # chunk_id → accumulated RRF score and metadata
    scores: dict[str, float] = {}
    vector_scores: dict[str, float] = {}
    keyword_ranks: dict[str, float] = {}
    chunk_data: dict[str, dict[str, Any]] = {}

    for rank, result in enumerate(vector_results, start=1):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1 / (k + rank)
        vector_scores[result.chunk_id] = result.score
        chunk_data[result.chunk_id] = {
            "doc_id": result.doc_id,
            "text": result.text,
            "metadata": result.metadata,
        }

    for rank, result in enumerate(keyword_results, start=1):
        scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1 / (k + rank)
        keyword_ranks[result.chunk_id] = result.rank
        if result.chunk_id not in chunk_data:
            chunk_data[result.chunk_id] = {
                "doc_id": result.doc_id,
                "text": result.text,
                "metadata": result.metadata,
            }

    logger.debug(f"Unique chunks after fusion: {len(scores)}")

    fused = []
    for chunk_id, rrf_score in scores.items():
        data = chunk_data[chunk_id]
        fused.append(
            FusedResult(
                chunk_id=chunk_id,
                doc_id=data["doc_id"],
                text=data["text"],
                rrf_score=rrf_score,
                vector_score=vector_scores.get(chunk_id),
                keyword_rank=keyword_ranks.get(chunk_id),
                metadata=data["metadata"],
            )
        )

    fused.sort(key=lambda r: r.rrf_score, reverse=True)
    fused = fused[:top_k]

    if fused:
        logger.debug(
            f"Top RRF score: {fused[0].rrf_score:.4f}, "
            f"bottom: {fused[-1].rrf_score:.4f}"
        )

    return fused


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _deduplicate(
    results: list[VectorSearchResult] | list[KeywordSearchResult],
    list_name: str,
) -> list:
    """Deduplicate by chunk_id, keeping highest-ranked (first) occurrence."""
    seen: set[str] = set()
    deduped = []
    for result in results:
        if result.chunk_id in seen:
            logger.warning(
                f"Duplicate chunk_id '{result.chunk_id}' in {list_name} results — "
                f"keeping highest-ranked occurrence"
            )
            continue
        seen.add(result.chunk_id)
        deduped.append(result)
    return deduped

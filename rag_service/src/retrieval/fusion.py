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
    vector_score: float | None  # None if chunk only in keyword results
    keyword_rank: float | None  # None if chunk only in vector results
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

    RRF combines ranked lists by position rather than score, making it robust
    to incompatible score scales between cosine similarity and ts_rank.

    For each chunk in either list:
        rrf_score += 1 / (k + rank)

    Chunks appearing in both lists accumulate contributions from each.

    Args:
        vector_results: Ranked results from vector search stage
        keyword_results: Ranked results from keyword search stage
        k: RRF constant — dampens advantage of top ranks (default 60)
        top_k: Maximum number of fused results to return

    Returns:
        List of FusedResult ordered by RRF score descending
    """
    if not vector_results and not keyword_results:
        return []

    if not isinstance(k, int) or k < 0:
        raise ValueError(f"k must be a non-negative integer, got {k!r}")

    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError(f"top_k must be a positive integer, got {top_k!r}")

    if not vector_results:
        logger.warning("Vector results empty — fusing keyword results only")

    if not keyword_results:
        logger.warning("Keyword results empty — fusing vector results only")

    logger.debug(
        f"Fusing {len(vector_results)} vector results + "
        f"{len(keyword_results)} keyword results"
    )

    deduped_vector = _deduplicate_vector(vector_results)
    deduped_keyword = _deduplicate_keyword(keyword_results)

    rrf_scores: dict[str, float] = {}
    vector_scores: dict[str, float] = {}
    keyword_ranks: dict[str, float] = {}
    chunk_data: dict[str, dict[str, Any]] = {}

    for rank, vr in enumerate(deduped_vector, start=1):
        cid = vr.chunk_id
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        vector_scores[cid] = vr.score
        chunk_data[cid] = {
            "doc_id": vr.doc_id,
            "text": vr.text,
            "metadata": vr.metadata,
        }

    for rank, kr in enumerate(deduped_keyword, start=1):
        cid = kr.chunk_id
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank)
        keyword_ranks[cid] = kr.rank
        if cid not in chunk_data:
            chunk_data[cid] = {
                "doc_id": kr.doc_id,
                "text": kr.text,
                "metadata": kr.metadata,
            }

    logger.debug(f"Unique chunks after fusion: {len(rrf_scores)}")

    fused: list[FusedResult] = [
        FusedResult(
            chunk_id=cid,
            doc_id=chunk_data[cid]["doc_id"],
            text=chunk_data[cid]["text"],
            rrf_score=score,
            vector_score=vector_scores.get(cid),
            keyword_rank=keyword_ranks.get(cid),
            metadata=chunk_data[cid]["metadata"],
        )
        for cid, score in rrf_scores.items()
    ]

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


def _deduplicate_vector(
    results: list[VectorSearchResult],
) -> list[VectorSearchResult]:
    """Keep first (highest-ranked) occurrence of each chunk_id."""
    seen: set[str] = set()
    deduped: list[VectorSearchResult] = []
    for vr in results:
        if vr.chunk_id in seen:
            logger.warning(
                f"Duplicate chunk_id '{vr.chunk_id}' found in vector "
                f"results — keeping highest-ranked occurrence"
            )
            continue
        seen.add(vr.chunk_id)
        deduped.append(vr)
    return deduped


def _deduplicate_keyword(
    results: list[KeywordSearchResult],
) -> list[KeywordSearchResult]:
    """Keep first (highest-ranked) occurrence of each chunk_id."""
    seen: set[str] = set()
    deduped: list[KeywordSearchResult] = []
    for kr in results:
        if kr.chunk_id in seen:
            logger.warning(
                f"Duplicate chunk_id '{kr.chunk_id}' found in keyword "
                f"results — keeping highest-ranked occurrence"
            )
            continue
        seen.add(kr.chunk_id)
        deduped.append(kr)
    return deduped

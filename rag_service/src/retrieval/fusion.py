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
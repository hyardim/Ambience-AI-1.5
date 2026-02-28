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
    pass
from __future__ import annotations

from math import exp
from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .fusion import FusedResult
from .query import RetrievalError

logger = setup_logger(__name__)

# Module-level model cache — loaded once on first call
_model = None
_model_name_loaded: str | None = None

LARGE_INPUT_WARNING_THRESHOLD = 50

# -----------------------------------------------------------------------
# Pydantic model
# -----------------------------------------------------------------------


class RankedResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    rerank_score: float
    rrf_score: float
    vector_score: float | None
    keyword_rank: float | None
    metadata: dict[str, Any]

# -----------------------------------------------------------------------
# Main functions
# -----------------------------------------------------------------------


def rerank(
    query: str,
    results: list[FusedResult],
    top_k: int = 10,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> list[RankedResult]:
    """
    Rerank fused candidates using a cross-encoder model.

    Scores each (query, chunk_text) pair using a cross-encoder, normalises
    logits to [0, 1] via sigmoid, and returns the top_k results by score.

    Args:
        query: Raw query string
        results: Fused candidates from reciprocal_rank_fusion / apply_filters
        top_k: Maximum number of results to return
        model_name: HuggingFace cross-encoder model identifier

    Returns:
        List of RankedResult ordered by rerank_score descending

    Raises:
        RetrievalError: If the model fails to load
    """
    pass


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _load_model(model_name: str) -> Any:
    """Load cross-encoder model, caching at module level."""
    global _model, _model_name_loaded

    if _model is not None and _model_name_loaded == model_name:
        return _model

    try:
        from sentence_transformers import CrossEncoder
        _model = CrossEncoder(model_name)
        _model_name_loaded = model_name
        logger.debug(f"Loaded cross-encoder model: {model_name}")
    except Exception as e:
        raise RetrievalError(
            stage="RERANK",
            query="",
            message=f"Failed to load cross-encoder model '{model_name}': {e}",
        ) from e

    return _model
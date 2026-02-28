from __future__ import annotations

from math import exp
from typing import Any

try:
    from sentence_transformers import CrossEncoder as _CrossEncoder
except ImportError:
    _CrossEncoder = None  # type: ignore[assignment,misc]

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .fusion import FusedResult
from .query import RetrievalError

logger = setup_logger(__name__)

# Module-level model cache — loaded once on first call
_model: Any | None = None
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
    if not results:
        return []

    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
        raise RetrievalError(
            stage="RERANK",
            query=query,
            message=f"top_k must be a positive integer, got {top_k!r}",
        )

    if len(results) > LARGE_INPUT_WARNING_THRESHOLD:
        logger.warning(
            f"Reranking {len(results)} candidates — "
            f"expected ≤{LARGE_INPUT_WARNING_THRESHOLD}. "
            f"Consider tightening fusion/filter top_k to reduce reranking cost."
        )

    logger.debug(f'Reranking {len(results)} candidates for query: "{query}"')

    model = _load_model(model_name)

    pairs = [(query, result.text) for result in results]

    try:
        import time

        start = time.perf_counter()
        logits = model.predict(pairs)
        elapsed_ms = (time.perf_counter() - start) * 1000
    except Exception as e:
        raise RetrievalError(
            stage="RERANK",
            query=query,
            message=f"Cross-encoder scoring failed: {e}",
        ) from e

    ranked: list[RankedResult] = []

    if len(logits) != len(results):
        raise RetrievalError(
            stage="RERANK",
            query=query,
            message=(
                "Cross-encoder returned a different number of scores than inputs "
                f"(logits={len(logits)}, results={len(results)})"
            ),
        )

    for result, logit in zip(results, logits, strict=False):
        try:
            score = _sigmoid(float(logit))
        except Exception as e:
            logger.warning(
                f"Failed to compute rerank score for chunk '{result.chunk_id}': {e} "
                f"— assigning score=0.0"
            )
            score = 0.0
        ranked.append(
            RankedResult(
                chunk_id=result.chunk_id,
                doc_id=result.doc_id,
                text=result.text,
                rerank_score=score,
                rrf_score=result.rrf_score,
                vector_score=result.vector_score,
                keyword_rank=result.keyword_rank,
                metadata=result.metadata,
            )
        )

    ranked.sort(key=lambda r: r.rerank_score, reverse=True)
    ranked = ranked[:top_k]

    logger.debug(f"Reranking complete in {elapsed_ms:.0f}ms")
    if ranked:
        logger.debug(
            f"Top rerank score: {ranked[0].rerank_score:.2f}, "
            f"bottom: {ranked[-1].rerank_score:.2f}"
        )
    logger.debug(f"Returning top {len(ranked)} after reranking")

    return ranked


def deduplicate(
    results: list[RankedResult],
    similarity_threshold: float = 0.85,
) -> list[RankedResult]:
    """
    Remove near-duplicate results using token-level Jaccard similarity.

    For each pair of results with Jaccard similarity above similarity_threshold,
    keeps the higher-scoring result and drops the other.

    Runs in O(n²) — acceptable for typical input sizes (≤30 results).

    Args:
        results: Reranked results from rerank()
        similarity_threshold: Jaccard similarity above which results are
                              considered duplicates (default 0.85)

    Returns:
        Deduplicated list preserving original ordering of kept results

    Raises:
        ValueError: If similarity_threshold is outside [0, 1]
    """
    if not results:
        return []

    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError(
            f"similarity_threshold must be between 0 and 1, "
            f"got {similarity_threshold!r}"
        )

    dropped: set[str] = set()

    for i, result_a in enumerate(results):
        if result_a.chunk_id in dropped:
            continue
        for result_b in results[i + 1 :]:
            if result_b.chunk_id in dropped:
                continue
            if (
                _jaccard_similarity(result_a.text, result_b.text)
                >= similarity_threshold
            ):
                if result_a.rerank_score >= result_b.rerank_score:
                    dropped.add(result_b.chunk_id)
                else:
                    dropped.add(result_a.chunk_id)
                    break

    deduped = [r for r in results if r.chunk_id not in dropped]

    if dropped:
        logger.debug(
            f"Deduplication: dropped {len(dropped)} near-duplicate results, "
            f"{len(deduped)} remaining"
        )

    return deduped


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _load_model(model_name: str) -> Any:
    """Load cross-encoder model, caching at module level."""
    global _model, _model_name_loaded

    if _model is not None and _model_name_loaded == model_name:
        return _model

    if _CrossEncoder is None:
        raise RetrievalError(
            stage="RERANK",
            query="",
            message=(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            ),
        )

    try:
        _model = _CrossEncoder(model_name)
        _model_name_loaded = model_name
        logger.debug(f"Loaded cross-encoder model: {model_name}")
    except Exception as e:
        raise RetrievalError(
            stage="RERANK",
            query="",
            message=f"Failed to load cross-encoder model '{model_name}': {e}",
        ) from e

    return _model


def _sigmoid(logit: float) -> float:
    """Normalise a logit to [0, 1] via sigmoid."""
    return 1.0 / (1.0 + exp(-logit))


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute token-level Jaccard similarity between two strings."""
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

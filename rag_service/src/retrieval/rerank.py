from __future__ import annotations

from math import exp, isfinite
from typing import Any

try:
    from sentence_transformers import CrossEncoder as _CrossEncoder
except ImportError:
    _CrossEncoder = None

from pydantic import BaseModel

from ..config import embed_config
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
    final_score: float = 0.0
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
    model_name: str = embed_config.reranker_model,
) -> list[RankedResult]:
    """Rerank fused candidates using a cross-encoder model.

    Scores each (query, chunk_text) pair using a cross-encoder, normalises
    logits to [0, 1] via sigmoid, and returns the top_k results by score.

    If the cross-encoder model fails to load **or** fails during scoring, a
    WARNING is logged and the results are returned in their existing (fusion)
    order with ``rerank_score=0.0`` so the pipeline degrades gracefully.

    Args:
        query: Raw query string.
        results: Fused candidates from reciprocal_rank_fusion / apply_filters.
        top_k: Maximum number of results to return.
        model_name: HuggingFace cross-encoder model identifier.

    Returns:
        List of RankedResult ordered by rerank_score descending.
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

    try:
        model = _load_model(model_name)
    except (RetrievalError, Exception) as e:
        logger.warning(
            "Cross-encoder model failed to load (%s); returning results in "
            "their current (fusion) order without reranking.",
            e,
        )
        return [
            RankedResult(
                chunk_id=r.chunk_id,
                doc_id=r.doc_id,
                text=r.text,
                rerank_score=0.0,
                final_score=0.0,
                rrf_score=r.rrf_score,
                vector_score=r.vector_score,
                keyword_rank=r.keyword_rank,
                metadata=r.metadata,
            )
            for r in results[:top_k]
        ]

    pairs = [(query, _enrich_text_for_reranking(result)) for result in results]

    try:
        import time

        start = time.perf_counter()
        logits = model.predict(pairs)
        elapsed_ms = (time.perf_counter() - start) * 1000
    except Exception as e:
        logger.warning(
            "Cross-encoder scoring failed (%s); returning results in their "
            "current order without reranking.",
            e,
        )
        return [
            RankedResult(
                chunk_id=r.chunk_id,
                doc_id=r.doc_id,
                text=r.text,
                rerank_score=0.0,
                final_score=0.0,
                rrf_score=r.rrf_score,
                vector_score=r.vector_score,
                keyword_rank=r.keyword_rank,
                metadata=r.metadata,
            )
            for r in results[:top_k]
        ]

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
            logit_f = float(logit)
            if not isfinite(logit_f):
                raise ValueError(f"non-finite logit: {logit_f}")
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
                final_score=score,
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

    token_sets = [_token_set(result.text) for result in results]
    token_lengths = [len(tokens) for tokens in token_sets]
    dropped: set[str] = set()

    for i, result_a in enumerate(results):
        if result_a.chunk_id in dropped:
            continue
        tokens_a = token_sets[i]
        len_a = token_lengths[i]
        for j in range(i + 1, len(results)):
            result_b = results[j]
            if result_b.chunk_id in dropped:
                continue
            tokens_b = token_sets[j]
            len_b = token_lengths[j]

            # Exact upper bound for Jaccard. If even max overlap cannot
            # reach threshold, skip the expensive intersection/union.
            if max(len_a, len_b) > 0:
                max_possible = min(len_a, len_b) / max(len_a, len_b)
                if max_possible < similarity_threshold:
                    continue

            if (
                _jaccard_similarity_from_sets(tokens_a, tokens_b)
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


def _enrich_text_for_reranking(result: FusedResult) -> str:
    """Prepend section context to chunk text for better cross-encoder scoring.

    The cross-encoder sees (query, text) pairs.  Including the section path
    and document title helps it distinguish clinically relevant chunks from
    chunks that share body-part keywords but come from unrelated sections
    (e.g. "ketogenic diets" vs "initial assessment").
    """
    metadata = getattr(result, "metadata", {}) or {}
    section_parts: list[str] = []

    title = metadata.get("title", "")
    if title:
        section_parts.append(title)

    section_path = metadata.get("section_path") or []
    if isinstance(section_path, list) and section_path:
        section_parts.append(" > ".join(str(s) for s in section_path))
    elif metadata.get("section_title"):
        section_parts.append(str(metadata["section_title"]))

    prefix = " — ".join(section_parts)
    text = getattr(result, "text", "")
    if prefix:
        return f"[{prefix}] {text}"
    return text


def _sigmoid(logit: float) -> float:
    """Normalise a logit to [0, 1] via sigmoid."""
    return 1.0 / (1.0 + exp(-logit))


def _token_set(text: str) -> set[str]:
    return set(text.lower().split())


def _jaccard_similarity_from_sets(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Compute exact Jaccard from precomputed token sets."""
    if not tokens_a and not tokens_b:
        return 1.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

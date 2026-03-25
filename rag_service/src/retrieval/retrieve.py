from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from ..config import path_config
from ..utils.logger import setup_logger
from ..utils.telemetry import append_jsonl
from .citation import CitedResult, assemble_citations
from .filters import FilterConfig, apply_filters
from .fusion import reciprocal_rank_fusion
from .keyword_search import keyword_search
from .query import RetrievalError, process_query
from .relevance import (
    document_kind_score,
    phrase_overlap_count,
    query_intent_alignment_score,
    query_overlap_count,
    query_overlap_ratio,
    text_quality_score,
)
from .rerank import deduplicate, rerank
from .vector_search import vector_search

logger = setup_logger(__name__)

DEBUG_ARTIFACT_DIR = path_config.data_debug / "retrieval"
RETRIEVAL_TELEMETRY_PATH = path_config.logs / "retrieval_metrics.jsonl"
BASE_SEARCH_CANDIDATE_MULTIPLIER = 4
LONG_QUERY_TOKEN_THRESHOLD = 8
LONG_QUERY_CANDIDATE_FLOOR = 40
FUSION_CANDIDATE_MULTIPLIER = 6
RERANK_CANDIDATE_MULTIPLIER = 2


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
    query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
    artifacts: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Stage 1: Query processing
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        processed = process_query(query, expand=expand_query)
    except RetrievalError:
        raise
    except Exception as e:
        raise RetrievalError(
            stage="QUERY",
            query=query,
            message=str(e),
        ) from e
    logger.debug(f"QUERY complete in {_ms(t)}ms")
    artifacts["01_query"] = processed.model_dump(exclude={"embedding"})
    candidate_top_k = _search_candidate_top_k(top_k, processed.expanded)
    fusion_top_k = max(top_k * FUSION_CANDIDATE_MULTIPLIER, candidate_top_k)
    rerank_top_k = top_k * RERANK_CANDIDATE_MULTIPLIER

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
            top_k=candidate_top_k,
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
            top_k=candidate_top_k,
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
            top_k=fusion_top_k,
        )
    except RetrievalError:
        raise
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
    except RetrievalError:
        raise
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
        reranked = rerank(query=query, results=filtered, top_k=rerank_top_k)
    except RetrievalError:
        raise
    except Exception as e:
        raise RetrievalError(stage="RERANK", query=query, message=str(e)) from e
    logger.debug(f"RERANK complete in {_ms(t)}ms")
    artifacts["06_rerank"] = [r.model_dump() for r in reranked]

    if not reranked:
        logger.warning(f'No results after reranking for query: "{query}"')
        _maybe_write_artifacts(write_debug_artifacts, query_hash, artifacts)
        return []

    if _rerank_is_uninformative(reranked):
        reranked = _fallback_sort_for_flat_rerank(query, reranked)
        artifacts["06_5_flat_rerank_fallback"] = [r.model_dump() for r in reranked]

    # ------------------------------------------------------------------
    # Stage 7: Deduplication
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        deduped = deduplicate(reranked)
    except RetrievalError:
        raise
    except Exception as e:
        raise RetrievalError(stage="DEDUP", query=query, message=str(e)) from e
    dropped = len(reranked) - len(deduped)
    logger.debug(f"DEDUP complete in {_ms(t)}ms, dropped {dropped}")
    artifacts["07_dedup"] = [r.model_dump() for r in deduped]

    # ------------------------------------------------------------------
    # Stage 7.5: Final score calibration
    # ------------------------------------------------------------------
    deduped = _apply_final_ranking(query, deduped, preferred_specialty=specialty)
    artifacts["07_5_final_ranking"] = [r.model_dump() for r in deduped]

    # ------------------------------------------------------------------
    # Stage 7.6: Document diversification
    # ------------------------------------------------------------------
    deduped = _diversify_by_document(deduped, max_per_doc=2)
    artifacts["07_6_doc_diversity"] = [r.model_dump() for r in deduped]

    # ------------------------------------------------------------------
    # Stage 8: Citations
    # ------------------------------------------------------------------
    t = time.perf_counter()
    try:
        cited = assemble_citations(deduped[:top_k])
    except RetrievalError:
        raise
    except Exception as e:
        raise RetrievalError(stage="CITATIONS", query=query, message=str(e)) from e
    logger.debug(f"CITATIONS complete in {_ms(t)}ms")
    artifacts["08_citations"] = [r.model_dump() for r in cited]

    total_ms = _ms(total_start)
    logger.info(f"Retrieval complete in {total_ms}ms, returning {len(cited)} results")
    append_jsonl(
        RETRIEVAL_TELEMETRY_PATH,
        {
            "query_hash": query_hash,
            "query_preview": query[:120],
            "top_k": top_k,
            "specialty": specialty,
            "source_name": source_name,
            "doc_type": doc_type,
            "expand_query": expand_query,
            "score_threshold": score_threshold,
            "vector_result_count": len(vector_results),
            "keyword_result_count": len(keyword_results),
            "fused_count": len(fused),
            "filtered_count": len(filtered),
            "reranked_count": len(reranked),
            "top_final_score": deduped[0].final_score if deduped else None,
            "returned_count": len(cited),
            "top_returned_score": cited[0].final_score if cited else None,
            "bottom_returned_score": cited[-1].final_score if cited else None,
            "vector_failed": vector_failed,
            "keyword_failed": keyword_failed,
            "latency_ms": total_ms,
        },
    )

    _maybe_write_artifacts(write_debug_artifacts, query_hash, artifacts)
    return cited


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _ms(start: float) -> int:
    """Convert elapsed perf_counter seconds to integer milliseconds."""
    return int((time.perf_counter() - start) * 1000)


def _search_candidate_top_k(top_k: int, query: str) -> int:
    """Select candidate depth for vector/keyword retrieval.

    Longer case-style queries tend to include many symptoms and modifiers.
    We widen retrieval depth for these queries so relevant chunks are not
    dropped before fusion/reranking.
    """
    base_top_k = top_k * BASE_SEARCH_CANDIDATE_MULTIPLIER
    query_tokens = query.split()
    if len(query_tokens) < LONG_QUERY_TOKEN_THRESHOLD:
        return base_top_k
    return max(base_top_k, LONG_QUERY_CANDIDATE_FLOOR)


def _keyword_signal(keyword_rank: float | None) -> float:
    if keyword_rank is None:
        return 0.0
    return 1.0 / (1.0 + max(float(keyword_rank), 0.0))


def _rerank_is_uninformative(results: list[Any]) -> bool:
    if len(results) < 2:
        return False
    scores = [float(getattr(result, "rerank_score", 0.0) or 0.0) for result in results]
    return max(scores) <= 0.0 or (max(scores) - min(scores)) <= 1e-9


def _fallback_sort_for_flat_rerank(query: str, results: list[Any]) -> list[Any]:
    def _fallback_key(result: Any) -> tuple[float, float, float, float, float]:
        text = getattr(result, "text", "")
        metadata = getattr(result, "metadata", {}) or {}
        title = metadata.get("title", "")
        section = metadata.get("section_title", "") or metadata.get("section_path", "")
        doc_type = metadata.get("doc_type", "")
        return (
            phrase_overlap_count(query, text) + phrase_overlap_count(query, title),
            query_intent_alignment_score(
                query,
                title=str(title),
                section=str(section),
                text=str(text),
                doc_type=str(doc_type),
            ),
            query_overlap_ratio(query, text),
            query_overlap_count(query, text) + query_overlap_count(query, title),
            float(getattr(result, "rrf_score", 0.0) or 0.0),
        )

    return sorted(results, key=_fallback_key, reverse=True)


def _calibrate_score(
    query: str,
    result: Any,
    *,
    preferred_specialty: str | None = None,
) -> float:
    rerank_score = max(float(getattr(result, "rerank_score", 0.0) or 0.0), 0.0)
    vector_score = max(float(getattr(result, "vector_score", 0.0) or 0.0), 0.0)
    keyword_signal = _keyword_signal(getattr(result, "keyword_rank", None))
    text = getattr(result, "text", "")
    overlap_count = query_overlap_count(query, text)
    phrase_count = phrase_overlap_count(query, text)
    metadata = getattr(result, "metadata", {}) or {}
    specialty_bonus = 0.0
    if preferred_specialty and metadata.get("specialty") == preferred_specialty:
        specialty_bonus = 0.04
    query_age = _extract_query_age(query)
    title_overlap = query_overlap_count(query, metadata.get("title", ""))
    title_phrase_count = phrase_overlap_count(query, metadata.get("title", ""))
    title_signal = min(title_overlap + (2 * title_phrase_count), 4) / 4.0
    section_text = " ".join(metadata.get("section_path") or [])
    document_signal = document_kind_score(
        title=metadata.get("title", ""),
        section=section_text,
        doc_type=metadata.get("doc_type", ""),
        source_name=metadata.get("source_name", ""),
    )
    intent_signal = query_intent_alignment_score(
        query,
        title=metadata.get("title", ""),
        section=section_text,
        text=text,
        doc_type=metadata.get("doc_type", ""),
    )
    section_overlap = query_overlap_count(query, section_text)
    section_phrase_count = phrase_overlap_count(query, section_text)
    section_signal = min(section_overlap + (2 * section_phrase_count), 4) / 4.0
    lexical_signal = min(overlap_count + (2 * phrase_count), 6) / 6.0
    structure_signal = max(title_signal, section_signal)
    structural_relevance = (
        min(
            title_overlap
            + section_overlap
            + (2 * (title_phrase_count + section_phrase_count)),
            6,
        )
        / 6.0
    )
    coverage_signal = query_overlap_ratio(
        query,
        " ".join([metadata.get("title", ""), section_text, text]),
    )
    quality_signal = text_quality_score(text)
    age_alignment = _age_alignment_score(
        query_age,
        " ".join(
            [
                metadata.get("title", ""),
                section_text,
                text,
            ]
        ),
    )

    blended = (
        (0.45 * rerank_score)
        + (0.3 * vector_score)
        + (0.08 * keyword_signal)
        + (0.12 * lexical_signal)
        + (0.08 * structure_signal)
        + (0.08 * structural_relevance)
        + (0.08 * coverage_signal)
        + document_signal
        + intent_signal
        + specialty_bonus
        + age_alignment
    )

    if quality_signal < 0.45 and structural_relevance < 0.5:
        blended -= 0.24
    elif quality_signal < 0.6 and structural_relevance < 0.34:
        blended -= 0.08

    if age_alignment >= 0:
        if phrase_count >= 1:
            blended = max(blended, vector_score * 1.08)
        elif overlap_count >= 2:
            blended = max(blended, vector_score)
        elif overlap_count >= 1 and vector_score >= 0.6:
            blended = max(blended, vector_score * 0.97)

    minimum_signal = rerank_score
    if age_alignment < 0:
        minimum_signal = rerank_score
    elif coverage_signal >= 0.3 or phrase_count >= 1:
        minimum_signal = max(minimum_signal, vector_score * 0.95)

    return min(max(blended, minimum_signal), 1.0)


def _extract_query_age(query: str) -> int | None:
    match = re.search(r"\b(\d{1,3})-year-old\b", query.lower())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _age_alignment_score(query_age: int | None, candidate_text: str) -> float:
    if query_age is None:
        return 0.0

    text = candidate_text.lower()
    child_markers = (
        "paediatric",
        "pediatric",
        "children",
        "child ",
        "young people",
        "infant",
        "neonatal",
        "under 16",
        "under 18",
    )
    adult_markers = (
        "adult",
        "adults",
        "over 16",
        "over 18",
    )

    has_child_marker = any(marker in text for marker in child_markers)
    has_adult_marker = any(marker in text for marker in adult_markers)

    if query_age >= 18:
        if has_child_marker:
            return -0.4
        if has_adult_marker:
            return 0.04
    else:
        if has_adult_marker:
            return -0.28
        if has_child_marker:
            return 0.04
    return 0.0


def _apply_final_ranking(
    query: str,
    results: list[Any],
    *,
    preferred_specialty: str | None = None,
) -> list[Any]:
    calibrated = []
    for result in results:
        final_score = _calibrate_score(
            query,
            result,
            preferred_specialty=preferred_specialty,
        )
        calibrated.append(result.model_copy(update={"final_score": final_score}))

    calibrated.sort(key=lambda item: item.final_score, reverse=True)

    preferred = (preferred_specialty or "").strip().casefold()
    if not preferred:
        return calibrated

    def _is_preferred(item: Any) -> bool:
        metadata = getattr(item, "metadata", {}) or {}
        specialty = (metadata.get("specialty") or "").strip().casefold()
        return bool(specialty and specialty == preferred)

    # Keep specialty preference soft: only prioritize if there is at least one
    # sufficiently strong hit in the requested specialty.
    viable_preferred = [
        item for item in calibrated if _is_preferred(item) and item.final_score >= 0.25
    ]
    if not viable_preferred:
        return calibrated

    preferred_items = [item for item in calibrated if _is_preferred(item)]
    non_preferred_items = [item for item in calibrated if not _is_preferred(item)]
    preferred_items.sort(key=lambda item: item.final_score, reverse=True)
    non_preferred_items.sort(key=lambda item: item.final_score, reverse=True)
    return preferred_items + non_preferred_items


def _maybe_write_artifacts(
    enabled: bool,
    query_hash: str,
    artifacts: dict[str, Any],
) -> None:
    """Write per-stage retrieval artifacts to disk when debug mode is enabled.

    Args:
        enabled: Whether debug artifact writing is turned on.
        query_hash: Short MD5 hash of the query, used as the output directory name.
        artifacts: Mapping of stage label to serialisable data.
    """
    if not enabled:
        return
    out_dir = DEBUG_ARTIFACT_DIR / query_hash
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in artifacts.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str))
    logger.debug(f"Debug artifacts written to {out_dir}")


def _diversify_by_document(
    results: list[Any],
    *,
    max_per_doc: int,
) -> list[Any]:
    if max_per_doc <= 0:
        return results

    unique_doc_ids = {
        getattr(result, "doc_id", "")
        for result in results
        if getattr(result, "doc_id", "")
    }
    if len(unique_doc_ids) <= 2:
        return results

    kept: list[Any] = []
    counts: dict[str, int] = {}
    for result in results:
        doc_id = getattr(result, "doc_id", "")
        if counts.get(doc_id, 0) >= max_per_doc:
            continue
        kept.append(result)
        counts[doc_id] = counts.get(doc_id, 0) + 1
    return kept

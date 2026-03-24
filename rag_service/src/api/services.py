from __future__ import annotations

import hashlib
from typing import Any

from ..config import db_config, path_config
from ..generation.client import ProviderName
from ..retrieval.citation import CitedResult
from ..retrieval.query import expand_query_text
from ..retrieval.relevance import (
    document_kind_score,
    phrase_overlap_count,
    query_intent_alignment_score,
    query_overlap_count,
    text_quality_score,
)
from ..retrieval.retrieve import retrieve
from ..utils.logger import setup_logger
from ..utils.telemetry import append_jsonl
from .citations import (
    MIN_RELEVANCE,
    has_query_overlap,
    is_boilerplate,
)
from .schemas import SearchResult

logger = setup_logger(__name__)
ROUTE_TELEMETRY_PATH = path_config.logs / "route_decisions.jsonl"
NO_EVIDENCE_RESPONSE = (
    "I couldn't find any guideline passage in the indexed sources that directly "
    "answers this question. Please rephrase the question, upload a supporting "
    "document, or try a different query."
)
HIGH_CONFIDENCE_RELEVANCE = 0.72
SOFT_FALLBACK_RELEVANCE = 0.45
LOW_SCORE_FALLBACK_FLOOR = 0.04
LOW_SCORE_FALLBACK_RATIO = 0.6
LOW_EVIDENCE_TOP_SCORE = 0.58
LOW_EVIDENCE_STRONG_HITS = 1


def _effective_relevance_score(result: CitedResult) -> float:
    """Prefer retrieval's calibrated final score, falling back safely if absent."""
    final_score = float(getattr(result, "final_score", 0.0) or 0.0)
    if final_score > 0:
        return final_score
    rerank_score = float(result.rerank_score or 0.0)
    vector_score = float(result.vector_score or 0.0)
    return max(rerank_score, vector_score)


def _citation_section_path(result: CitedResult) -> str:
    return " > ".join(result.citation.section_path)


def _cited_result_to_chunk(result: CitedResult) -> dict[str, Any]:
    citation = result.citation
    metadata = {
        "title": citation.title,
        "source_name": citation.source_name,
        "filename": citation.title,
        "specialty": citation.specialty,
        "doc_type": citation.doc_type,
        "creation_date": citation.creation_date,
        "publish_date": citation.publish_date,
        "last_updated_date": citation.last_updated_date,
        "source_url": citation.source_url,
        "content_type": citation.content_type,
        "rerank_score": result.rerank_score,
        "vector_score": result.vector_score,
        "rrf_score": result.rrf_score,
        "keyword_rank": result.keyword_rank,
    }
    return {
        "text": result.text,
        "score": _effective_relevance_score(result),
        "doc_id": citation.doc_id,
        "doc_version": None,
        "chunk_id": citation.chunk_id,
        "chunk_index": None,
        "content_type": citation.content_type,
        "page_start": citation.page_start,
        "page_end": citation.page_end,
        "section_path": _citation_section_path(result),
        "metadata": metadata,
    }


def to_search_result(res: dict[str, Any]) -> SearchResult:
    metadata = res.get("metadata") or {}
    return SearchResult(
        text=res["text"],
        source=(
            metadata.get("title")
            or metadata.get("source_name")
            or metadata.get("filename")
            or "Unknown Source"
        ),
        score=res["score"],
        doc_id=res.get("doc_id"),
        doc_version=res.get("doc_version"),
        chunk_id=res.get("chunk_id"),
        chunk_index=res.get("chunk_index"),
        content_type=res.get("content_type"),
        page_start=res.get("page_start"),
        page_end=res.get("page_end"),
        section_path=res.get("section_path"),
        creation_date=metadata.get("creation_date"),
        publish_date=metadata.get("publish_date"),
        last_updated_date=metadata.get("last_updated_date"),
        metadata=metadata,
    )


def retrieve_chunks(
    query: str,
    *,
    top_k: int,
    specialty: str | None,
) -> list[dict[str, Any]]:
    chunks = [
        _cited_result_to_chunk(result)
        for result in retrieve(
            query=query,
            db_url=db_config.database_url,
            top_k=top_k,
            specialty=specialty,
            expand_query=True,
        )
    ]
    chunks.sort(key=lambda chunk: float(chunk.get("score", 0.0)), reverse=True)
    return chunks


def retrieve_chunks_advanced(
    query: str,
    *,
    top_k: int,
    specialty: str | None,
    source_name: str | None,
    doc_type: str | None,
    score_threshold: float,
    expand_query: bool,
) -> list[dict[str, Any]]:
    chunks = [
        _cited_result_to_chunk(result)
        for result in retrieve(
            query=query,
            db_url=db_config.database_url,
            top_k=top_k,
            specialty=specialty,
            source_name=source_name,
            doc_type=doc_type,
            score_threshold=score_threshold,
            expand_query=expand_query,
        )
    ]
    chunks.sort(key=lambda chunk: float(chunk.get("score", 0.0)), reverse=True)
    return chunks


def _filter_chunks(
    query: str,
    retrieved: list[dict[str, Any]],
    specialty: str | None,
) -> list[dict[str, Any]]:
    expanded_query = expand_query_text(query)

    def _raw_query_overlap(chunk: dict[str, Any]) -> bool:
        return has_query_overlap(query, chunk.get("text", ""))

    def _expanded_query_overlap(chunk: dict[str, Any]) -> bool:
        return expanded_query != query and has_query_overlap(
            expanded_query,
            chunk.get("text", ""),
        )

    base_candidates = [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= MIN_RELEVANCE
        and ((chunk.get("metadata") or {}).get("source_url") or chunk.get("doc_id"))
    ]
    if not base_candidates:
        if not retrieved:
            return []
        top_score = max(float(chunk.get("score", 0.0)) for chunk in retrieved)
        if top_score < LOW_SCORE_FALLBACK_FLOOR:
            return []
        low_score_threshold = max(
            LOW_SCORE_FALLBACK_FLOOR,
            top_score * LOW_SCORE_FALLBACK_RATIO,
        )
        low_score_fallback = [
            chunk
            for chunk in retrieved
            if chunk.get("score", 0) >= low_score_threshold
            and ((chunk.get("metadata") or {}).get("source_url") or chunk.get("doc_id"))
            and _raw_query_overlap(chunk)
        ]
        return _sort_by_alignment(
            low_score_fallback,
            expanded_query,
            specialty=specialty,
        )

    alignments = [
        _alignment_details(expanded_query, chunk) for chunk in base_candidates
    ]
    filtered = [
        chunk
        for chunk, alignment in zip(base_candidates, alignments, strict=False)
        if not (is_boilerplate(chunk) and alignment["total"] < 3)
    ]
    if not filtered:
        return []

    strict_matches = [
        chunk
        for chunk in filtered
        if _raw_query_overlap(chunk)
        or (
            _expanded_query_overlap(chunk)
            and chunk.get("score", 0) >= SOFT_FALLBACK_RELEVANCE
        )
        or chunk.get("score", 0) >= HIGH_CONFIDENCE_RELEVANCE
    ]
    if strict_matches:
        alignments = [
            _alignment_details(expanded_query, chunk) for chunk in strict_matches
        ]
        max_title_section_overlap = max(
            alignment["title_section_overlap"] for alignment in alignments
        )
        max_text_phrases = max(alignment["text_phrases"] for alignment in alignments)
        if max_title_section_overlap >= 2 or max_text_phrases >= 1:
            narrowed = [
                chunk
                for chunk, alignment in zip(strict_matches, alignments, strict=False)
                if (
                    alignment["title_section_overlap"] == max_title_section_overlap
                    and max_title_section_overlap >= 2
                )
                or (
                    alignment["text_phrases"] == max_text_phrases
                    and max_text_phrases >= 1
                )
            ]
            if narrowed:
                return _sort_by_alignment(
                    narrowed,
                    expanded_query,
                    specialty=specialty,
                )
        refined = [
            chunk
            for chunk, alignment in zip(strict_matches, alignments, strict=False)
            if (
                alignment["total"] >= 5
                or alignment["text_phrases"] >= 1
                or alignment["title_section_overlap"] >= 2
            )
        ]
        if refined:
            return _sort_by_alignment(
                refined,
                expanded_query,
                specialty=specialty,
            )
        return _sort_by_alignment(
            strict_matches,
            expanded_query,
            specialty=specialty,
        )

    semantic_alignments = [
        _alignment_details(expanded_query, chunk) for chunk in filtered
    ]
    semantic_fallback = [
        chunk
        for chunk, alignment in zip(filtered, semantic_alignments, strict=False)
        if chunk.get("score", 0) >= SOFT_FALLBACK_RELEVANCE
        and (
            chunk.get("score", 0) >= HIGH_CONFIDENCE_RELEVANCE
            or (
            alignment["total"] >= 3
            or alignment["text_phrases"] >= 1
            or alignment["title_section_overlap"] >= 1
            )
        )
    ]
    if semantic_fallback:
        return _sort_by_alignment(
            semantic_fallback,
            expanded_query,
            specialty=specialty,
        )

    top_score = max(float(chunk.get("score", 0.0)) for chunk in filtered)
    low_score_threshold = max(
        LOW_SCORE_FALLBACK_FLOOR,
        top_score * LOW_SCORE_FALLBACK_RATIO,
    )
    low_score_fallback = [
        chunk
        for chunk in filtered
        if chunk.get("score", 0) >= low_score_threshold
        and _raw_query_overlap(chunk)
    ]
    return low_score_fallback


def filter_chunks(
    query: str,
    retrieved: list[dict[str, Any]],
    *,
    specialty: str | None = None,
) -> list[dict[str, Any]]:
    return _filter_chunks(query, retrieved, specialty=specialty)


def _alignment_details(query: str, chunk: dict[str, Any]) -> dict[str, int]:
    metadata = chunk.get("metadata") or {}
    text = chunk.get("text") or ""
    title = metadata.get("title") or metadata.get("source_name") or ""
    section = chunk.get("section_path") or metadata.get("section_title") or ""
    text_overlap = query_overlap_count(query, text)
    title_overlap = query_overlap_count(query, title)
    section_overlap = query_overlap_count(query, section)
    text_phrases = phrase_overlap_count(query, text)
    title_phrases = phrase_overlap_count(query, title)
    section_phrases = phrase_overlap_count(query, section)
    return {
        "total": (
            text_overlap
            + title_overlap
            + section_overlap
            + (2 * (text_phrases + title_phrases + section_phrases))
        ),
        "text_phrases": text_phrases,
        "title_section_overlap": (
            title_overlap + section_overlap + (2 * (title_phrases + section_phrases))
        ),
    }


def _sort_by_alignment(
    chunks: list[dict[str, Any]],
    query: str,
    *,
    specialty: str | None,
) -> list[dict[str, Any]]:
    preferred = (specialty or "").strip().casefold()

    def _specialty_match(chunk: dict[str, Any]) -> int:
        if not preferred:
            return 0
        metadata = chunk.get("metadata") or {}
        chunk_specialty = (metadata.get("specialty") or "").strip().casefold()
        return int(bool(chunk_specialty and chunk_specialty == preferred))

    def _document_score(chunk: dict[str, Any]) -> float:
        metadata = chunk.get("metadata") or {}
        return document_kind_score(
            title=metadata.get("title", ""),
            section=chunk.get("section_path") or metadata.get("section_title") or "",
            doc_type=metadata.get("doc_type", ""),
            source_name=metadata.get("source_name", ""),
        )

    def _intent_score(chunk: dict[str, Any]) -> float:
        metadata = chunk.get("metadata") or {}
        return query_intent_alignment_score(
            query,
            title=metadata.get("title", ""),
            section=chunk.get("section_path") or metadata.get("section_title") or "",
            text=chunk.get("text") or "",
            doc_type=metadata.get("doc_type", ""),
        )

    return sorted(
        chunks,
        key=lambda chunk: (
            _specialty_match(chunk),
            _intent_score(chunk),
            _document_score(chunk),
            _alignment_details(query, chunk)["title_section_overlap"],
            _alignment_details(query, chunk)["total"]
            + text_quality_score(chunk.get("text") or ""),
            float(chunk.get("score", 0.0)),
        ),
        reverse=True,
    )


def evidence_level(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "none"

    scores = [float(chunk.get("score", 0.0)) for chunk in chunks]
    top_score = scores[0]
    strong_hits = sum(1 for score in scores[:3] if score >= LOW_EVIDENCE_TOP_SCORE)
    if top_score < LOW_EVIDENCE_TOP_SCORE or strong_hits <= LOW_EVIDENCE_STRONG_HITS:
        return "weak"
    return "strong"


def low_evidence_note(level: str) -> str | None:
    if level != "weak":
        return None
    return (
        "Indexed guideline support is limited for this question. If the context "
        "does not directly support a claim, say so explicitly and keep any "
        "general context clearly separated."
    )


def query_fingerprint(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]


def log_route_decision(
    endpoint: str,
    provider: ProviderName,
    route_score: float,
    threshold: float,
    reasons: tuple[str, ...],
    *,
    query: str | None = None,
    retrieved_count: int | None = None,
    top_score: float | None = None,
    evidence: str | None = None,
    outcome: str | None = None,
) -> None:
    logger.info(
        "%s routing provider=%s score=%s threshold=%s reasons=%s",
        endpoint,
        provider,
        route_score,
        threshold,
        ",".join(reasons) or "none",
    )
    append_jsonl(
        ROUTE_TELEMETRY_PATH,
        {
            "endpoint": endpoint,
            "provider": provider,
            "score": route_score,
            "threshold": threshold,
            "reasons": list(reasons),
            "query_hash": query_fingerprint(query) if query else None,
            "retrieved_count": retrieved_count,
            "top_score": top_score,
            "evidence": evidence,
            "outcome": outcome,
        },
    )

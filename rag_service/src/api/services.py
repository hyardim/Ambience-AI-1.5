from __future__ import annotations

import hashlib
import re
from typing import Any

from ..config import db_config, path_config
from ..generation.client import ProviderName
from ..retrieval.citation import CitedResult
from ..retrieval.retrieve import retrieve
from ..utils.logger import setup_logger
from ..utils.telemetry import append_jsonl
from .citations import MIN_RELEVANCE, has_query_overlap, is_boilerplate
from .schemas import SearchResult

logger = setup_logger(__name__)
ROUTE_TELEMETRY_PATH = path_config.logs / "route_decisions.jsonl"
NO_EVIDENCE_RESPONSE = (
    "I couldn't find any guideline passage in the indexed sources that directly "
    "answers this question. Please rephrase the question, upload a supporting "
    "document, or try a different query."
)
HIGH_CONFIDENCE_RELEVANCE = 0.72
SOFT_FALLBACK_RELEVANCE = 0.55
LOW_SCORE_FALLBACK_FLOOR = 0.0
LOW_SCORE_FALLBACK_RATIO = 0.5
LOW_EVIDENCE_TOP_SCORE = 0.58
LOW_EVIDENCE_STRONG_HITS = 1
REFERRAL_SECTION_HINT_RE = re.compile(
    r"\b(recommendation|recommendations|refer|referral|pathway|"
    r"when to refer|urgent|immediate)\b",
    re.IGNORECASE,
)
NON_DIRECTIVE_SECTION_HINT_RE = re.compile(
    r"\b(discussion|results|context|background|rationale|headlines|"
    r"why the committee made)\b",
    re.IGNORECASE,
)
INVESTIGATION_QUERY_HINT_RE = re.compile(
    r"\b(investigations?|investigate|baseline|blood tests?|work[- ]?up|"
    r"laboratory|labs?)\b",
    re.IGNORECASE,
)
INVESTIGATION_TEXT_HINT_RE = re.compile(
    r"\b(investigations?|blood tests?|fbc|cbc|esr|crp|urinalysis|"
    r"anti-?ccp|rheumatoid factor|rf\b|ana|dsdna|u&es|egfr|creatinine)\b",
    re.IGNORECASE,
)
IMAGING_QUERY_HINT_RE = re.compile(
    r"\b(imaging|x-?ray|ultrasound|mri|ct|scan)\b",
    re.IGNORECASE,
)
IMAGING_TEXT_HINT_RE = re.compile(
    r"\b(x-?ray|ultrasound|mri|ct|scan|imaging)\b",
    re.IGNORECASE,
)
REFERRAL_QUERY_HINT_RE = re.compile(
    r"\b(refer\w*|referr\w*|pathway|urgent|immediate|urgency|"
    r"prior to referral|before referral)\b",
    re.IGNORECASE,
)
REFERRAL_TEXT_HINT_RE = re.compile(
    r"\b(refer\w*|referr\w*|pathway|urgent|urgency)\b",
    re.IGNORECASE,
)
SOURCE_NAME_PRIORITY: dict[str, int] = {
    "nice": 2,
    "sign": 1,
}


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
    }
    return {
        "text": result.text,
        "score": result.rerank_score,
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
    return [
        _cited_result_to_chunk(result)
        for result in retrieve(
            query=query,
            db_url=db_config.database_url,
            top_k=top_k,
            specialty=specialty,
        )
    ]


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
    return [
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


def filter_chunks(query: str, retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base_candidates = [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= MIN_RELEVANCE
        and ((chunk.get("metadata") or {}).get("source_url") or chunk.get("doc_id"))
        and not is_boilerplate(chunk)
    ]

    strict_matches = [
        chunk
        for chunk in base_candidates
        if has_query_overlap(query, chunk.get("text", ""))
        or chunk.get("score", 0) >= HIGH_CONFIDENCE_RELEVANCE
    ]
    if strict_matches:
        return _rank_by_query_overlap(query, strict_matches)

    semantic_fallback = [
        chunk
        for chunk in base_candidates
        if chunk.get("score", 0) >= SOFT_FALLBACK_RELEVANCE
    ]
    if semantic_fallback:
        return _rank_by_query_overlap(query, semantic_fallback)

    if not retrieved:
        return []

    top_score = max(float(chunk.get("score", 0.0)) for chunk in retrieved)
    low_score_threshold = max(
        LOW_SCORE_FALLBACK_FLOOR,
        top_score * LOW_SCORE_FALLBACK_RATIO,
    )
    low_score_matches = [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= low_score_threshold
        and ((chunk.get("metadata") or {}).get("source_url") or chunk.get("doc_id"))
        and has_query_overlap(query, chunk.get("text", ""))
        and not is_boilerplate(chunk)
    ]
    return _rank_by_query_overlap(query, low_score_matches)


def _rank_by_query_overlap(
    query: str, chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Prioritise section fit, requested-part coverage, overlap, then score."""
    if not chunks:
        return []
    return sorted(
        chunks,
        key=lambda chunk: (
            _section_priority(query, chunk),
            _query_part_coverage_score(query, chunk),
            _query_overlap_count(query, chunk.get("text", "")),
            _source_name_priority(chunk),
            float(chunk.get("score", 0.0)),
        ),
        reverse=True,
    )


def _section_priority(query: str, chunk: dict[str, Any]) -> int:
    """Bias ranking toward recommendation/referral sections for pathway queries."""
    section_path = (chunk.get("section_path") or "").lower()
    if not section_path:
        return 0

    priority = 0
    if REFERRAL_QUERY_HINT_RE.search(query):
        if REFERRAL_SECTION_HINT_RE.search(section_path):
            priority += 2
        if NON_DIRECTIVE_SECTION_HINT_RE.search(section_path):
            priority -= 1
    return priority


def _query_overlap_count(query: str, text: str) -> int:
    """Count overlapping lexical terms between query and chunk text."""

    def _tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[A-Za-z0-9]+", value.lower())
            if len(token) >= 3
        }

    return len(_tokens(query).intersection(_tokens(text)))


def _requested_query_parts(query: str) -> set[str]:
    parts: set[str] = set()
    if INVESTIGATION_QUERY_HINT_RE.search(query):
        parts.add("investigations")
    if IMAGING_QUERY_HINT_RE.search(query):
        parts.add("imaging")
    if REFERRAL_QUERY_HINT_RE.search(query):
        parts.add("referral")
    return parts


def _query_part_coverage_score(query: str, chunk: dict[str, Any]) -> int:
    requested_parts = _requested_query_parts(query)
    if not requested_parts:
        return 0

    haystack = f"{chunk.get('text', '')} {chunk.get('section_path', '')}"
    score = 0
    if "investigations" in requested_parts and INVESTIGATION_TEXT_HINT_RE.search(
        haystack
    ):
        score += 1
    if "imaging" in requested_parts and IMAGING_TEXT_HINT_RE.search(haystack):
        score += 1
    if "referral" in requested_parts and REFERRAL_TEXT_HINT_RE.search(haystack):
        score += 1
    return score


def _source_name_priority(chunk: dict[str, Any]) -> int:
    source_name = str((chunk.get("metadata") or {}).get("source_name") or "").lower()
    return SOURCE_NAME_PRIORITY.get(source_name, 0)


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
    canonicalization_triggered: bool | None = None,
    selected_retrieval_pass: str | None = None,
    fallback_reason: str | None = None,
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
            "canonicalization_triggered": canonicalization_triggered,
            "selected_retrieval_pass": selected_retrieval_pass,
            "fallback_reason": fallback_reason,
        },
    )

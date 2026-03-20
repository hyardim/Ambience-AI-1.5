from __future__ import annotations

import hashlib
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
LOW_EVIDENCE_TOP_SCORE = 0.58
LOW_EVIDENCE_STRONG_HITS = 1


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
    return [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= MIN_RELEVANCE
        and ((chunk.get("metadata") or {}).get("source_url") or chunk.get("doc_id"))
        and (
            has_query_overlap(query, chunk.get("text", ""))
            or chunk.get("score", 0) >= HIGH_CONFIDENCE_RELEVANCE
        )
        and not is_boilerplate(chunk)
    ]


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

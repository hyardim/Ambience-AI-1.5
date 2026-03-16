from __future__ import annotations

from typing import Any

from ..config import db_config
from ..generation.client import ProviderName
from ..retrieval.citation import CitedResult
from ..retrieval.retrieve import retrieve
from ..utils.logger import setup_logger
from .citations import MIN_RELEVANCE, has_query_overlap, is_boilerplate
from .schemas import SearchResult

logger = setup_logger(__name__)


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
        "source_path": citation.source_url,
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


def filter_chunks(query: str, retrieved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        chunk
        for chunk in retrieved
        if chunk.get("score", 0) >= MIN_RELEVANCE
        and (chunk.get("metadata") or {}).get("source_path")
        and has_query_overlap(query, chunk.get("text", ""))
        and not is_boilerplate(chunk)
    ]


def log_route_decision(
    endpoint: str,
    provider: ProviderName,
    route_score: float,
    threshold: float,
    reasons: tuple[str, ...],
) -> None:
    logger.info(
        "%s routing provider=%s score=%s threshold=%s reasons=%s",
        endpoint,
        provider,
        route_score,
        threshold,
        ",".join(reasons) or "none",
    )

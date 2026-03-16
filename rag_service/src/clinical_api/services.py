from __future__ import annotations

from typing import Any

from ..generation.client import ProviderName
from ..ingestion.embed import embed_text
from ..retrieval.vector_store import search_similar_chunks
from ..utils.logger import setup_logger
from .citations import MIN_RELEVANCE, has_query_overlap, is_boilerplate
from .schemas import SearchResult
from .startup import get_embedding_model

logger = setup_logger(__name__)


def to_search_result(res: dict[str, Any]) -> SearchResult:
    metadata = res.get("metadata") or {}
    return SearchResult(
        text=res["text"],
        source=metadata.get("filename", "Unknown Source"),
        score=res["score"],
        doc_id=res.get("doc_id"),
        doc_version=res.get("doc_version"),
        chunk_id=res.get("chunk_id"),
        chunk_index=res.get("chunk_index"),
        content_type=res.get("content_type"),
        page_start=res.get("page_start"),
        page_end=res.get("page_end"),
        section_path=res.get("section_path"),
        metadata=metadata,
    )


def embed_query_text(query: str) -> list[float]:
    embeddings_result = embed_text(
        get_embedding_model(),
        [query],
        batch_size=1,
    )
    return embeddings_result[0]


def retrieve_chunks(
    query: str,
    *,
    top_k: int,
    specialty: str | None,
) -> list[dict[str, Any]]:
    return search_similar_chunks(
        embed_query_text(query),
        limit=top_k,
        specialty=specialty,
    )


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

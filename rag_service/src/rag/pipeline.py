from __future__ import annotations

from src.rag.generate import RAGResponse, generate
from src.retrieval.retrieve import retrieve


def ask(
    *,
    query: str,
    db_url: str,
    top_k: int = 5,
    specialty: str | None = None,
    source_name: str | None = None,
    doc_type: str | None = None,
    score_threshold: float = 0.3,
    expand_query: bool = False,
    settings=None,
) -> RAGResponse:
    """Full RAG pipeline: retrieve context then generate an answer."""

    context = retrieve(
        query=query,
        db_url=db_url,
        top_k=top_k,
        specialty=specialty,
        source_name=source_name,
        doc_type=doc_type,
        score_threshold=score_threshold,
        expand_query=expand_query,
    )
    return generate(query=query, context=context, settings=settings)

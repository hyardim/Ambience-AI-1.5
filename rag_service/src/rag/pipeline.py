from __future__ import annotations

from src.config import llm_config
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
    if not context:
        # Graceful fallback when no supporting evidence is available.
        return RAGResponse(
            answer=(
                "Sorry, I do not have sufficient supporting sources to answer this "
                "question."
            ),
            sources=[],
            query=query,
            model=getattr(settings, "llm_model", llm_config.llm_model),
        )

    return generate(query=query, context=context, settings=settings)

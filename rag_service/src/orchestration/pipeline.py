from __future__ import annotations

from src.api.services import NO_EVIDENCE_RESPONSE, evidence_level, low_evidence_note
from src.config import llm_config
from src.orchestration.generate import RAGResponse, generate
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
    settings: object | None = None,
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
        # Return a fixed response when retrieval returns no supporting context.
        return RAGResponse(
            answer=NO_EVIDENCE_RESPONSE,
            sources=[],
            query=query,
            model=getattr(settings, "llm_model", llm_config.llm_model),
        )

    evidence = evidence_level(
        [{"score": source.rerank_score} for source in context]
    )
    return generate(
        query=query,
        context=context,
        settings=settings,
        evidence_note=low_evidence_note(evidence),
    )

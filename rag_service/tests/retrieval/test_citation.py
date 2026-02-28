from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.citation import (
    Citation,
    CitationError,
    CitedResult,
    assemble_citations,
    format_citation,
    format_section_path,
)
from src.retrieval.rerank import RankedResult

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_metadata(
    title: str = "Gout: diagnosis and management",
    source_name: str = "NICE",
    specialty: str = "rheumatology",
    doc_type: str = "guideline",
    source_url: str = "https://www.nice.org.uk/guidance/cg56",
    content_type: str = "text",
    section_path: list[str] | None = None,
    section_title: str = "Treatment",
    page_start: int | None = 12,
    page_end: int | None = 13,
) -> dict[str, Any]:
    return {
        "title": title,
        "source_name": source_name,
        "specialty": specialty,
        "doc_type": doc_type,
        "source_url": source_url,
        "content_type": content_type,
        "section_path": (
            section_path
            if section_path is not None
            else ["Treatment", "Urate-lowering therapy"]
        ),
        "section_title": section_title,
        "page_start": page_start,
        "page_end": page_end,
    }


def make_ranked_result(
    chunk_id: str = "chunk_001",
    text: str = "Allopurinol is recommended as first-line urate-lowering therapy.",
    rerank_score: float = 0.91,
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_rank: float | None = 0.72,
    metadata: dict[str, Any] | None = None,
) -> RankedResult:
    return RankedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text=text,
        rerank_score=rerank_score,
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_rank,
        metadata=metadata if metadata is not None else make_metadata(),
    )

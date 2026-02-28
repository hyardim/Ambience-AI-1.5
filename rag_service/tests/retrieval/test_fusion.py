from __future__ import annotations

from typing import Any

from src.retrieval.fusion import FusedResult, reciprocal_rank_fusion
from src.retrieval.keyword_search import KeywordSearchResult
from src.retrieval.vector_search import VectorSearchResult

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_vector_result(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    score: float = 0.85,
    metadata: dict[str, Any] | None = None,
) -> VectorSearchResult:
    return VectorSearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=text,
        score=score,
        metadata=metadata or {"specialty": "rheumatology"},
    )

def make_keyword_result(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    rank: float = 0.72,
    metadata: dict[str, Any] | None = None,
) -> KeywordSearchResult:
    return KeywordSearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=text,
        rank=rank,
        metadata=metadata or {"specialty": "rheumatology"},
    )
from __future__ import annotations

from math import exp
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.fusion import FusedResult
from src.retrieval.query import RetrievalError
from src.retrieval.rerank import (
    RankedResult,
    _jaccard_similarity,
    deduplicate,
    rerank,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_fused_result(
    chunk_id: str = "chunk_001",
    text: str = "Some clinical text about methotrexate dosage.",
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_rank: float | None = 0.72,
    metadata: dict[str, Any] | None = None,
) -> FusedResult:
    return FusedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text=text,
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_rank,
        metadata=metadata or {"specialty": "rheumatology"},
    )


def make_ranked_result(
    chunk_id: str = "chunk_001",
    text: str = "Some clinical text about methotrexate dosage.",
    rerank_score: float = 0.85,
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
        metadata=metadata or {"specialty": "rheumatology"},
    )


def make_mock_model(logits: list[float]) -> MagicMock:
    mock = MagicMock()
    mock.predict.return_value = logits
    return mock


QUERY = "methotrexate dosage rheumatoid arthritis"


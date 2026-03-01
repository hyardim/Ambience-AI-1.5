from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.citation import Citation, CitedResult
from src.retrieval.fusion import FusedResult
from src.retrieval.keyword_search import KeywordSearchResult
from src.retrieval.query import ProcessedQuery, RetrievalError
from src.retrieval.rerank import RankedResult
from src.retrieval.vector_search import VectorSearchResult

QUERY = "gout treatment options"
DB_URL = "postgresql://localhost/test"

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_processed_query() -> ProcessedQuery:
    return ProcessedQuery(
        original="gout treatment options",
        expanded="gout treatment options urate hyperuricemia",
        embedding=[0.1] * 384,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )


def make_vector_result(chunk_id: str = "c1") -> VectorSearchResult:
    return VectorSearchResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        score=0.85,
        metadata={"specialty": "rheumatology"},
    )

def make_keyword_result(chunk_id: str = "c1") -> KeywordSearchResult:
    return KeywordSearchResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        rank=0.72,
        metadata={"specialty": "rheumatology"},
    )

def make_fused_result(chunk_id: str = "c1") -> FusedResult:
    return FusedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        metadata={"specialty": "rheumatology"},
    )

def make_ranked_result(chunk_id: str = "c1") -> RankedResult:
    return RankedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        rerank_score=0.91,
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        metadata={"specialty": "rheumatology"},
    )

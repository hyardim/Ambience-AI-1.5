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

def make_cited_result(chunk_id: str = "c1") -> CitedResult:
    return CitedResult(
        chunk_id=chunk_id,
        text="Some text about gout.",
        rerank_score=0.91,
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        citation=Citation(
            title="Gout: diagnosis and management",
            source_name="NICE",
            specialty="rheumatology",
            doc_type="guideline",
            section_path=["Treatment"],
            section_title="Treatment",
            page_start=12,
            page_end=13,
            source_url="https://www.nice.org.uk/guidance/cg56",
            doc_id="doc_001",
            chunk_id=chunk_id,
            content_type="text",
        ),
    )

def make_all_stage_mocks(
    vector_results: list | None = None,
    keyword_results: list | None = None,
    fused_results: list | None = None,
    filtered_results: list | None = None,
    reranked_results: list | None = None,
    deduped_results: list | None = None,
    cited_results: list | None = None,
) -> dict[str, MagicMock]:
    return {
        "process_query": MagicMock(return_value=make_processed_query()),
        "vector_search": MagicMock(
            return_value=vector_results if vector_results is not None else [make_vector_result()]
        ),
        "keyword_search": MagicMock(
            return_value=keyword_results if keyword_results is not None else [make_keyword_result()]
        ),
        "reciprocal_rank_fusion": MagicMock(
            return_value=fused_results if fused_results is not None else [make_fused_result()]
        ),
        "apply_filters": MagicMock(
            return_value=filtered_results if filtered_results is not None else [make_fused_result()]
        ),
        "rerank": MagicMock(
            return_value=reranked_results if reranked_results is not None else [make_ranked_result()]
        ),
        "deduplicate": MagicMock(
            return_value=deduped_results if deduped_results is not None else [make_ranked_result()]
        ),
        "assemble_citations": MagicMock(
            return_value=cited_results if cited_results is not None else [make_cited_result()]
        ),
    }

def run_retrieve(mocks: dict[str, MagicMock], **kwargs):
    from src.retrieval.retrieve import retrieve
    with patch("src.retrieval.retrieve.process_query", mocks["process_query"]), \
         patch("src.retrieval.retrieve.vector_search", mocks["vector_search"]), \
         patch("src.retrieval.retrieve.keyword_search", mocks["keyword_search"]), \
         patch("src.retrieval.retrieve.reciprocal_rank_fusion", mocks["reciprocal_rank_fusion"]), \
         patch("src.retrieval.retrieve.apply_filters", mocks["apply_filters"]), \
         patch("src.retrieval.retrieve.rerank", mocks["rerank"]), \
         patch("src.retrieval.retrieve.deduplicate", mocks["deduplicate"]), \
         patch("src.retrieval.retrieve.assemble_citations", mocks["assemble_citations"]):
        return retrieve(QUERY, DB_URL, **kwargs)

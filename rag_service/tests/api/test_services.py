from __future__ import annotations

import pytest

from src.api.schemas import SearchResult
from src.api.services import (
    filter_chunks,
    retrieve_chunks,
    to_search_result,
)
from src.retrieval.citation import Citation, CitedResult


def test_filter_chunks_drops_low_quality_hits() -> None:
    kept = {
        "text": "migraine treatment guidance",
        "score": 0.9,
        "metadata": {"source_path": "/tmp/doc.pdf"},
    }
    dropped = {
        "text": "supplementary material",
        "score": 0.1,
        "metadata": {},
    }

    filtered = filter_chunks("migraine treatment", [kept, dropped])

    assert filtered == [kept]


def test_retrieve_chunks_uses_shared_retrieval_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, int, str | None]] = []

    citation = Citation(
        title="Migraine Guide",
        source_name="NICE",
        specialty="neurology",
        doc_type="guideline",
        section_path=["Treatment"],
        section_title="Treatment",
        page_start=2,
        page_end=3,
        source_url="https://example.com/guide",
        doc_id="doc-1",
        chunk_id="chunk-1",
        content_type="text",
    )
    result = CitedResult(
        chunk_id="chunk-1",
        text="chunk",
        rerank_score=0.8,
        rrf_score=0.7,
        vector_score=0.6,
        keyword_rank=0.5,
        citation=citation,
    )

    def fake_retrieve(
        query: str,
        db_url: str,
        *,
        top_k: int,
        specialty: str | None,
    ) -> list[CitedResult]:
        calls.append((query, db_url, top_k, specialty))
        return [result]

    monkeypatch.setattr("src.api.services.retrieve", fake_retrieve)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    chunks = retrieve_chunks("headache", top_k=3, specialty="neurology")

    assert chunks == [
        {
            "text": "chunk",
            "score": 0.8,
            "doc_id": "doc-1",
            "doc_version": None,
            "chunk_id": "chunk-1",
            "chunk_index": None,
            "content_type": "text",
            "page_start": 2,
            "page_end": 3,
            "section_path": "Treatment",
            "metadata": {
                "title": "Migraine Guide",
                "source_name": "NICE",
                "filename": "Migraine Guide",
                "specialty": "neurology",
                "doc_type": "guideline",
                "creation_date": None,
                "publish_date": None,
                "last_updated_date": None,
                "source_url": "https://example.com/guide",
                "source_path": "https://example.com/guide",
                "content_type": "text",
            },
        }
    ]
    assert calls == [("headache", "postgresql://x", 3, "neurology")]


def test_to_search_result_uses_default_source_name() -> None:
    result = to_search_result({"text": "chunk", "score": 0.6})

    assert result == SearchResult(
        text="chunk",
        source="Unknown Source",
        score=0.6,
        metadata={},
    )


def test_to_search_result_prefers_title_then_source_name() -> None:
    result = to_search_result(
        {
            "text": "chunk",
            "score": 0.9,
            "metadata": {
                "title": "NICE Migraine Guideline",
                "source_name": "NICE",
                "filename": "migraine.pdf",
            },
        }
    )

    assert result.source == "NICE Migraine Guideline"

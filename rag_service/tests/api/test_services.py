from __future__ import annotations

import pytest

from src.api.schemas import SearchResult
from src.api.services import (
    NO_EVIDENCE_RESPONSE,
    evidence_level,
    filter_chunks,
    log_route_decision,
    low_evidence_note,
    query_fingerprint,
    retrieve_chunks,
    to_search_result,
)
from src.retrieval.citation import Citation, CitedResult


def test_filter_chunks_drops_low_quality_hits() -> None:
    kept = {
        "text": "migraine treatment guidance",
        "score": 0.9,
        "metadata": {"source_url": "https://example.com/doc.pdf"},
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
                "source_path": None,
                "content_type": "text",
            },
        }
    ]
    assert calls == [("headache", "postgresql://x", 3, "neurology")]


def test_filter_chunks_keeps_high_confidence_semantic_hit_without_token_overlap() -> (
    None
):
    retrieved = [
        {
            "text": "Acetylsalicylic acid may be recommended in select scenarios.",
            "score": 0.82,
            "metadata": {"source_url": "https://example.com/doc.pdf"},
        }
    ]

    filtered = filter_chunks("aspirin management", retrieved)

    assert filtered == retrieved


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


def test_evidence_level_handles_none_weak_and_strong_cases() -> None:
    assert evidence_level([]) == "none"
    assert evidence_level([{"score": 0.57}]) == "weak"
    assert evidence_level([{"score": 0.57}, {"score": 0.61}, {"score": 0.4}]) == "weak"
    assert evidence_level([{"score": 0.9}, {"score": 0.8}, {"score": 0.61}]) == "strong"


def test_low_evidence_note_only_returns_text_for_weak_level() -> None:
    assert low_evidence_note("strong") is None
    assert low_evidence_note("none") is None
    assert "limited" in (low_evidence_note("weak") or "")


def test_query_fingerprint_is_stable() -> None:
    assert query_fingerprint("migraine treatment") == query_fingerprint(
        "migraine treatment"
    )
    assert len(query_fingerprint("migraine treatment")) == 12


def test_log_route_decision_records_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payloads: list[tuple[object, object]] = []

    monkeypatch.setattr(
        "src.api.services.append_jsonl",
        lambda path, payload: payloads.append((path, payload)),
    )

    log_route_decision(
        "/answer",
        "cloud",
        0.8,
        0.5,
        ("high_complexity",),
        query="How do I manage RRMS?",
        retrieved_count=3,
        top_score=0.91,
        evidence="strong",
        outcome=NO_EVIDENCE_RESPONSE,
    )

    assert payloads
    _, payload = payloads[0]
    assert payload["endpoint"] == "/answer"
    assert payload["provider"] == "cloud"
    assert payload["reasons"] == ["high_complexity"]
    assert payload["retrieved_count"] == 3
    assert payload["top_score"] == 0.91
    assert payload["evidence"] == "strong"
    assert payload["outcome"] == NO_EVIDENCE_RESPONSE
    assert isinstance(payload["query_hash"], str)

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


def test_filter_chunks_falls_back_to_semantic_candidates_when_strict_match_empty() -> (
    None
):
    retrieved = [
        {
            "text": "Acetylsalicylic acid may be considered for secondary prevention.",
            "score": 0.62,
            "metadata": {"source_url": "https://example.com/doc.pdf"},
        }
    ]

    filtered = filter_chunks("aspirin management", retrieved)

    assert filtered == retrieved


def test_filter_chunks_semantic_fallback_keeps_low_relevance_out() -> None:
    retrieved = [
        {
            "text": "Acetylsalicylic acid may be considered for secondary prevention.",
            "score": 0.44,
            "metadata": {"source_url": "https://example.com/doc.pdf"},
        }
    ]

    filtered = filter_chunks("aspirin management", retrieved)

    assert filtered == []


def test_filter_chunks_uses_guarded_low_score_fallback_for_near_top_hits() -> None:
    top_hit = {
        "text": (
            "SLE with proteinuria and rising creatinine needs urgent renal pathway."
        ),
        "score": 0.047,
        "metadata": {"source_url": "https://example.com/doc.pdf"},
    }
    lower_hit = {
        "text": "SLE proteinuria context with less specific detail.",
        "score": 0.03,
        "metadata": {"source_url": "https://example.com/doc.pdf"},
    }

    filtered = filter_chunks(
        "SLE proteinuria rising creatinine referral",
        [top_hit, lower_hit],
    )

    assert filtered == [top_hit, lower_hit]


def test_filter_chunks_low_score_fallback_preserves_weak_overlap_when_available() -> (
    None
):
    retrieved = [
        {
            "text": "SLE and proteinuria mention only briefly.",
            "score": 0.02,
            "metadata": {"source_url": "https://example.com/doc.pdf"},
        }
    ]

    filtered = filter_chunks("SLE proteinuria referral", retrieved)

    assert filtered == retrieved


def test_filter_chunks_keeps_hits_with_doc_id_even_without_public_source_url() -> None:
    retrieved = [
        {
            "text": "Use beta interferon for indicated patients.",
            "score": 0.9,
            "metadata": {"source_path": "/app/data/raw/doc.pdf"},
            "doc_id": "legacy-doc-1",
        }
    ]

    filtered = filter_chunks("beta interferon", retrieved)

    assert filtered == retrieved


def test_filter_chunks_drops_hits_without_source_url_or_doc_id() -> None:
    retrieved = [
        {
            "text": "Use beta interferon for indicated patients.",
            "score": 0.9,
            "metadata": {"source_path": "/app/data/raw/doc.pdf"},
        }
    ]

    filtered = filter_chunks("beta interferon", retrieved)

    assert filtered == []


def test_filter_chunks_prioritises_higher_query_overlap_over_raw_score() -> None:
    high_score_low_overlap = {
        "text": "Refer urgently for sudden-onset unsteady gait.",
        "score": 0.14,
        "metadata": {"source_url": "https://example.com/doc-a.pdf"},
    }
    lower_score_high_overlap = {
        "text": (
            "Refer adults with rapidly progressive unsteady gait and consider "
            "normal pressure hydrocephalus if gait apraxia is present."
        ),
        "score": 0.06,
        "metadata": {"source_url": "https://example.com/doc-b.pdf"},
    }

    filtered = filter_chunks(
        (
            "rapidly progressive gait disturbance with possible normal pressure "
            "hydrocephalus"
        ),
        [high_score_low_overlap, lower_score_high_overlap],
    )

    assert filtered[0] == lower_score_high_overlap


def test_filter_chunks_keeps_very_high_score_signal_ahead_of_overlap_noise() -> None:
    high_score_core_recommendation = {
        "text": (
            "Patients with severe SLE should be investigated to exclude infection "
            "before treatment decisions."
        ),
        "score": 0.99,
        "metadata": {"source_url": "https://example.com/core-guideline.pdf"},
    }
    lower_score_overlap_noise = {
        "text": (
            "Severe SLE treatment decisions infection exclusion context and "
            "discussion wording repeated for narrative overlap."
        ),
        "score": 0.18,
        "metadata": {"source_url": "https://example.com/discussion.pdf"},
    }

    filtered = filter_chunks(
        "severe SLE alternative aetiologies infection before treatment decisions",
        [lower_score_overlap_noise, high_score_core_recommendation],
    )

    assert filtered[0] == high_score_core_recommendation


def test_filter_chunks_prefers_referral_sections_for_pathway_queries() -> None:
    discussion_chunk = {
        "text": (
            "SLE proteinuria rising creatinine details with broad contextual "
            "commentary and limited pathway instructions."
        ),
        "score": 0.91,
        "section_path": "CLINICAL SCIENCE > Discussion",
        "metadata": {"source_url": "https://example.com/paper.pdf"},
    }
    referral_chunk = {
        "text": (
            "Refer urgently to nephrology for suspected lupus nephritis when "
            "proteinuria and creatinine are rising."
        ),
        "score": 0.62,
        "section_path": "Recommendations > Referral pathway",
        "metadata": {"source_url": "https://example.com/guideline.pdf"},
    }

    filtered = filter_chunks(
        (
            "patient with known SLE presenting with new proteinuria and rising "
            "creatinine. What immediate investigations and referral pathway are "
            "recommended?"
        ),
        [discussion_chunk, referral_chunk],
    )

    assert filtered[0] == referral_chunk


def test_filter_chunks_prefers_treatment_chunks_for_treatment_queries() -> None:
    context_chunk = {
        "text": (
            "Lupus nephritis cohort findings show moderate proteinuria in "
            "a subset of patients."
        ),
        "score": 0.91,
        "section_path": "CLINICAL SCIENCE > Results",
        "metadata": {"source_url": "https://example.com/results.pdf"},
    }
    treatment_chunk = {
        "text": (
            "ACE inhibitors or ARBs are recommended for moderate proteinuria "
            "to reduce proteinuria and protect renal function."
        ),
        "score": 0.62,
        "section_path": "Recommendations > Treatment",
        "metadata": {"source_url": "https://example.com/recommendations.pdf"},
    }

    filtered = filter_chunks(
        (
            "In lupus nephritis with moderate proteinuria, what does guidance "
            "say about ACE inhibitor or ARB use?"
        ),
        [context_chunk, treatment_chunk],
    )

    assert filtered[0] == treatment_chunk


def test_filter_chunks_prefers_chunk_covering_requested_query_parts() -> None:
    referral_only_chunk = {
        "text": (
            "Adults with suspected persistent synovitis should be referred "
            "within 3 working days."
        ),
        "score": 0.99,
        "section_path": "Recommendations > Referral pathway",
        "metadata": {
            "source_url": "https://example.com/audit.pdf",
            "source_name": "BSR",
        },
    }
    investigations_and_imaging_chunk = {
        "text": (
            "Offer rheumatoid factor testing, consider anti-CCP if RF negative, "
            "and X-ray the hands and feet before referral."
        ),
        "score": 0.96,
        "section_path": "Recommendations > Referral from primary care",
        "metadata": {
            "source_url": "https://example.com/nice.pdf",
            "source_name": "NICE",
        },
    }

    filtered = filter_chunks(
        (
            "What baseline blood tests and imaging should be completed prior "
            "to referral?"
        ),
        [referral_only_chunk, investigations_and_imaging_chunk],
    )

    assert filtered[0] == investigations_and_imaging_chunk


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


def test_retrieve_chunks_advanced_returns_mapped_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line 113: retrieve_chunks_advanced function return."""
    from src.api.services import retrieve_chunks_advanced

    citation = Citation(
        title="Advanced Guide",
        source_name="NICE",
        specialty="cardiology",
        doc_type="guideline",
        section_path=["Overview"],
        section_title="Overview",
        page_start=1,
        page_end=2,
        source_url="https://example.com/adv",
        doc_id="doc-adv",
        chunk_id="chunk-adv",
        content_type="text",
    )
    result = CitedResult(
        chunk_id="chunk-adv",
        text="advanced chunk",
        rerank_score=0.85,
        rrf_score=0.7,
        vector_score=0.6,
        keyword_rank=0.5,
        citation=citation,
    )

    monkeypatch.setattr("src.api.services.retrieve", lambda **kwargs: [result])
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    chunks = retrieve_chunks_advanced(
        "chest pain",
        top_k=5,
        specialty="cardiology",
        source_name="NICE",
        doc_type="guideline",
        score_threshold=0.3,
        expand_query=False,
    )

    assert len(chunks) == 1
    assert chunks[0]["text"] == "advanced chunk"
    assert chunks[0]["score"] == 0.85
    assert chunks[0]["doc_id"] == "doc-adv"
    assert chunks[0]["chunk_id"] == "chunk-adv"


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
        canonicalization_triggered=True,
        selected_retrieval_pass="canonical",
        fallback_reason="low_confidence_retrieval",
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
    assert payload["canonicalization_triggered"] is True
    assert payload["selected_retrieval_pass"] == "canonical"
    assert payload["fallback_reason"] == "low_confidence_retrieval"
    assert isinstance(payload["query_hash"], str)

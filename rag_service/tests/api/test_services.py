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


def test_filter_chunks_prefers_more_specific_overlap_when_present() -> None:
    retrieved = [
        {
            "text": "Refer adults with progressive gait symptoms urgently.",
            "score": 0.7,
            "metadata": {"source_url": "https://example.com/a"},
        },
        {
            "text": "Normal pressure hydrocephalus can cause gait apraxia.",
            "score": 0.6,
            "metadata": {"source_url": "https://example.com/b"},
        },
    ]

    filtered = filter_chunks(
        "65-year-old with gait disturbance and urinary incontinence. "
        "Should normal pressure hydrocephalus be suspected?",
        retrieved,
    )

    assert filtered == [retrieved[1]]


def test_filter_chunks_drops_weakly_aligned_distractors_when_strong_match_exists() -> (
    None
):
    strong = {
        "text": (
            "Normal pressure hydrocephalus is an important cause of gait apraxia."
        ),
        "score": 0.53,
        "section_path": "Difficulty initiating and coordinating walking (gait apraxia)",
        "metadata": {
            "title": "Suspected neurological conditions: recognition and referral",
            "source_url": "https://example.com/nph",
        },
    }
    weak = {
        "text": "Stroke services should agree protocols for symptomatic hydrocephalus.",
        "score": 0.44,
        "section_path": "Avoiding aspiration pneumonia",
        "metadata": {
            "title": "Stroke and transient ischaemic attack in over 16s",
            "source_url": "https://example.com/stroke",
        },
    }

    filtered = filter_chunks(
        "65-year-old with rapidly progressive gait disturbance and urinary "
        "incontinence over 3 months. CT head shows ventriculomegaly. "
        "Should normal pressure hydrocephalus be suspected?",
        [strong, weak],
    )

    assert filtered == [strong]


def test_filter_chunks_keeps_relevant_referral_template_when_alignment_is_strong() -> (
    None
):
    relevant = {
        "text": (
            "Thank you for this referral. We have not offered an appointment "
            "because the referral did not include sufficient details. According "
            "to the BSR PMR guideline, a patient with polymyalgia rheumatica "
            "and typical shoulder and hip girdle pain can usually start steroids "
            "in primary care unless red flags are present."
        ),
        "score": 0.63,
        "section_path": "ANCA, Suspected vasculitis > Polymyalgia Rheumatica (PMR)",
        "metadata": {
            "title": "Bsr Enhanced Triage And Specialist Advice",
            "source_url": "https://example.com/pmr",
        },
    }
    noisy = {
        "text": "predominant shoulder and thigh symptoms symmetrical autoantibodies "
        "vasculitis other CTDs occult and deep sepsis",
        "score": 0.9,
        "section_path": "Guidelines > Diagnosis",
        "metadata": {
            "title": "kep303a 186..190",
            "source_url": "https://example.com/noisy",
        },
    }

    filtered = filter_chunks(
        "70-year-old with sudden onset bilateral shoulder and hip girdle pain "
        "with morning stiffness >1 hour and raised ESR. Should polymyalgia "
        "rheumatica be started on steroids in primary care?",
        [noisy, relevant],
    )

    assert filtered[0] == relevant


def test_filter_chunks_prefers_guidance_style_doc_over_appraisal_for_triage_query() -> (
    None
):
    appraisal = {
        "text": "Biologic treatment may be considered after DMARD failure.",
        "score": 0.6,
        "section_path": "Clinical need and practice",
        "metadata": {
            "title": (
                "Adalimumab, etanercept, infliximab and abatacept for treating "
                "moderate rheumatoid arthritis after conventional DMARDs have failed"
            ),
            "doc_type": "appraisal",
            "source_url": "https://example.com/appraisal",
            "specialty": "rheumatology",
        },
    }
    guidance = {
        "text": (
            "Refer suspected early inflammatory arthritis promptly and obtain "
            "baseline tests."
        ),
        "score": 0.58,
        "section_path": "Suspected early inflammatory arthritis referral",
        "metadata": {
            "title": "Bsr Enhanced Triage And Specialist Advice",
            "doc_type": "guideline",
            "source_url": "https://example.com/guidance",
            "specialty": "rheumatology",
        },
    }

    filtered = filter_chunks(
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. "
        "What baseline blood tests and imaging should be completed prior to referral?",
        [appraisal, guidance],
        specialty="rheumatology",
    )

    assert filtered[0] == guidance


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
        final_score=0.74,
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
        expand_query: bool,
    ) -> list[CitedResult]:
        calls.append((query, db_url, top_k, specialty, expand_query))
        return [result]

    monkeypatch.setattr("src.api.services.retrieve", fake_retrieve)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    chunks = retrieve_chunks("headache", top_k=3, specialty="neurology")

    assert chunks == [
        {
            "text": "chunk",
            "score": 0.74,
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
                "rerank_score": 0.8,
                "vector_score": 0.6,
                "rrf_score": 0.7,
                "keyword_rank": 0.5,
            },
        }
    ]
    assert calls == [("headache", "postgresql://x", 3, "neurology", True)]


def test_retrieve_chunks_prefers_vector_score_when_reranker_undershoots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citation = Citation(
        title="Referral Guidance",
        source_name="NICE",
        specialty="rheumatology",
        doc_type="guideline",
        section_path=["Referral"],
        section_title="Referral",
        page_start=6,
        page_end=6,
        source_url="https://example.com/referral",
        doc_id="doc-ref",
        chunk_id="chunk-ref",
        content_type="text",
    )
    result = CitedResult(
        chunk_id="chunk-ref",
        text="Refer any adult with suspected persistent synovitis.",
        rerank_score=0.01,
        final_score=0.58,
        rrf_score=0.2,
        vector_score=0.58,
        keyword_rank=0.1,
        citation=citation,
    )

    monkeypatch.setattr("src.api.services.retrieve", lambda **kwargs: [result])

    chunks = retrieve_chunks(
        "What baseline blood tests and imaging should be completed prior to referral?",
        top_k=3,
        specialty="rheumatology",
    )

    assert chunks[0]["score"] == pytest.approx(0.58)
    assert chunks[0]["metadata"]["rerank_score"] == pytest.approx(0.01)
    assert chunks[0]["metadata"]["vector_score"] == pytest.approx(0.58)


def test_retrieve_chunks_resorts_results_by_effective_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citation = Citation(
        title="Guide A",
        source_name="NICE",
        specialty="neurology",
        doc_type="guideline",
        section_path=["Assessment"],
        section_title="Assessment",
        page_start=1,
        page_end=1,
        source_url="https://example.com/a",
        doc_id="doc-a",
        chunk_id="chunk-a",
        content_type="text",
    )
    weaker = CitedResult(
        chunk_id="chunk-a",
        text="weaker",
        rerank_score=0.4,
        final_score=0.4,
        rrf_score=0.2,
        vector_score=0.1,
        keyword_rank=0.1,
        citation=citation,
    )
    stronger = CitedResult(
        chunk_id="chunk-b",
        text="stronger",
        rerank_score=0.01,
        final_score=0.7,
        rrf_score=0.2,
        vector_score=0.7,
        keyword_rank=0.1,
        citation=citation.model_copy(
            update={"doc_id": "doc-b", "chunk_id": "chunk-b", "title": "Guide B"}
        ),
    )

    monkeypatch.setattr(
        "src.api.services.retrieve",
        lambda **kwargs: [weaker, stronger],
    )

    chunks = retrieve_chunks("query", top_k=2, specialty="neurology")

    assert [chunk["chunk_id"] for chunk in chunks] == ["chunk-b", "chunk-a"]


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


def test_filter_chunks_semantic_fallback_rejects_unaligned_general_context() -> None:
    retrieved = [
        {
            "text": "General lifestyle advice about celebrations and food preferences.",
            "score": 0.58,
            "metadata": {"source_url": "https://example.com/doc.pdf"},
        }
    ]

    filtered = filter_chunks("best pizza topping for a birthday party", retrieved)

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

    assert filtered == [top_hit]


def test_filter_chunks_low_score_fallback_ignores_very_low_top_scores() -> None:
    retrieved = [
        {
            "text": "SLE and proteinuria mention only briefly.",
            "score": 0.02,
            "metadata": {"source_url": "https://example.com/doc.pdf"},
        }
    ]

    filtered = filter_chunks("SLE proteinuria referral", retrieved)

    assert filtered == []


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


def test_filter_chunks_drops_blank_source_url_without_doc_id() -> None:
    retrieved = [
        {
            "text": "Use beta interferon for indicated patients.",
            "score": 0.9,
            "metadata": {"source_url": "   "},
        }
    ]

    filtered = filter_chunks("beta interferon", retrieved)

    assert filtered == []


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


def test_filter_chunks_low_score_fallback_returns_alignment_sorted_results() -> None:
    weaker = {
        "text": "SLE creatinine issue is mentioned briefly.",
        "score": 0.048,
        "section_path": "General renal issues",
        "metadata": {
            "title": "General Rheumatology Notes",
            "source_url": "https://example.com/weaker",
            "specialty": "rheumatology",
        },
    }
    stronger = {
        "text": (
            "SLE with proteinuria and rising creatinine needs urgent renal pathway."
        ),
        "score": 0.047,
        "section_path": "Lupus nephritis > Renal red flags",
        "metadata": {
            "title": "Bsr Enhanced Triage And Specialist Advice",
            "source_url": "https://example.com/stronger",
            "specialty": "rheumatology",
        },
    }

    filtered = filter_chunks(
        "SLE proteinuria rising creatinine referral",
        [weaker, stronger],
        specialty="rheumatology",
    )

    assert filtered == [stronger, weaker]


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

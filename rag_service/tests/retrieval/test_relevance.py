from __future__ import annotations

from src.retrieval.relevance import (
    document_kind_score,
    query_intent_alignment_score,
    query_overlap_ratio,
    text_quality_score,
)


def test_query_overlap_ratio_empty_query() -> None:
    assert query_overlap_ratio("a", "some candidate text") == 0.0


def test_query_overlap_ratio_empty_candidate() -> None:
    assert query_overlap_ratio("migraine treatment", "a b") == 0.0


def test_query_overlap_ratio_partial_coverage() -> None:
    ratio = query_overlap_ratio("migraine treatment plan", "migraine pain relief")
    assert 0.0 < ratio < 1.0


def test_text_quality_score_empty_string() -> None:
    assert text_quality_score("") == 0.0


def test_text_quality_score_numbers_only() -> None:
    assert text_quality_score("123 456 789") == 0.0


def test_text_quality_score_normal_text() -> None:
    score = text_quality_score("Normal pressure hydrocephalus is a treatable condition")
    assert score > 0.5


def test_document_kind_score_opaque_product_code_title() -> None:
    score = document_kind_score(title="NG12 Suspected cancer")
    assert score < 0.0


def test_document_kind_score_opaque_compound_code_title() -> None:
    score = document_kind_score(title="CG-TA12 some product")
    assert score < 0.0


def test_intent_alignment_surgical_query_demotes_surgical_doc() -> None:
    score = query_intent_alignment_score(
        "What urgent investigations are needed before referral?",
        title="Joint replacement (primary): hip, knee and shoulder",
        section="Implants for primary elective hip replacement",
        text="Surgical approaches for hip replacement include posterior approach.",
        doc_type="guideline",
    )
    assert score < 0


def test_intent_alignment_returns_zero_for_non_intent_query() -> None:
    score = query_intent_alignment_score(
        "Tell me about general health",
        title="Some guideline",
        section="Overview",
        text="General information about health.",
    )
    assert score == 0.0

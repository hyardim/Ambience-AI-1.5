from __future__ import annotations

import re

from src.api.citations import (
    _enforce_partial_question_coverage,
    _enforce_requested_scope,
    _has_cited_sentence_matching,
    _join_labels,
    _question_focus_text,
    extract_citation_results,
    has_query_overlap,
    is_boilerplate,
    parse_citation_group,
    query_overlap_count,
)
from src.api.schemas import SearchResult
from src.retrieval.relevance import phrase_overlap_count


def test_extract_citation_results_can_strip_references() -> None:
    citations = [
        SearchResult(text="A", source="S", score=0.9),
        SearchResult(text="B", source="S", score=0.8),
    ]

    answer, used = extract_citation_results(
        "Use [2]\n\nReferences: ignored",
        citations,
        strip_references=True,
    )

    assert answer == "Use [1]"
    assert used == [citations[1]]


def test_parse_citation_group_skips_invalid_values() -> None:
    assert parse_citation_group("1, x, 5-a") == [1]


def test_has_query_overlap_accepts_three_character_tokens() -> None:
    assert has_query_overlap(
        "DVT prophylaxis in CKD",
        "CKD patients need DVT prevention",
    )


def test_query_overlap_count_prefers_specific_medical_terms() -> None:
    query = (
        "65-year-old with gait disturbance and urinary incontinence. "
        "Should normal pressure hydrocephalus be suspected?"
    )
    exact = "Normal pressure hydrocephalus can cause gait apraxia."
    vague = "Refer adults with progressive gait symptoms urgently."

    assert query_overlap_count(query, exact) > query_overlap_count(query, vague)
    assert has_query_overlap(query, exact) is True


def test_phrase_overlap_count_detects_clinical_red_flag_phrases() -> None:
    query = "Severe back pain with urinary retention and bilateral leg weakness."
    matching = (
        "This guideline does not cover cauda equina syndrome with urinary "
        "retention or progressive neurological deficit."
    )
    vague = "Refer adults with limb symptoms for specialist review."

    assert phrase_overlap_count(query, matching) > phrase_overlap_count(query, vague)


def test_is_boilerplate_flags_operational_referral_letters() -> None:
    chunk = {
        "text": "Thank you for this referral. We have not offered an appointment.",
        "section_path": "Non-specific back pain referral",
    }

    assert is_boilerplate(chunk) is True


def test_extract_citation_results_drops_uncited_clinical_sentences() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Refer urgently [1]. Consider extra hydration advice while waiting.",
        citations,
        strip_references=False,
    )

    assert answer == "Refer urgently [1]."
    assert used == [citations[0]]


def test_extract_citation_results_drops_rule_style_citation_tokens() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Refer to neurology [1.4.4].",
        citations,
        strip_references=False,
    )

    assert answer == ""
    assert used == []


def test_extract_citation_results_normalizes_section_reference_artifacts() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Refer to neurology to exclude NPH ([1] 1.4.4).",
        citations,
        strip_references=False,
    )

    assert answer == "Refer to neurology to exclude NPH [1]."
    assert used == [citations[0]]


def test_extract_citation_results_strips_leading_page_label_artifacts() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Page 13 Refer immediately for cauda equina syndrome [1].",
        citations,
        strip_references=False,
    )

    assert answer == "Refer immediately for cauda equina syndrome [1]."
    assert used == [citations[0]]


def test_extract_citation_results_adds_partial_coverage_note() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Immediate investigations include urinalysis [1].",
        citations,
        strip_references=False,
        query=(
            "Patient with new proteinuria and rising creatinine. "
            "What immediate investigations and referral pathway are recommended?"
        ),
    )

    assert answer.startswith("Immediate investigations include urinalysis [1].")
    assert "referral/urgency pathway part of this question" in answer
    assert used == [citations[0]]


def test_extract_citation_results_drops_treatment_when_not_requested() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        (
            "Immediate investigations include urinalysis [1]. "
            "Start ACE inhibitors for proteinuria [1]."
        ),
        citations,
        strip_references=False,
        query=(
            "Patient with SLE and new proteinuria. "
            "What immediate investigations and referral pathway are recommended?"
        ),
    )

    assert "urinalysis [1]" in answer
    assert "ace inhibitors" not in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_started_on_treatment_queries() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "PMR can be started on prednisolone 15-20 mg daily in primary care [1].",
        citations,
        strip_references=False,
        query=(
            "70-year-old with sudden onset bilateral shoulder and hip girdle pain. "
            "Should polymyalgia rheumatica be started on steroids in primary care?"
        ),
    )

    assert "prednisolone 15-20 mg daily" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_initiation_queries() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Methotrexate can be initiated in primary care after baseline blood tests [1].",
        citations,
        strip_references=False,
        query=(
            "Can methotrexate be initiated in primary care for inflammatory "
            "arthritis?"
        ),
    )

    assert "initiated in primary care" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_initial_management_queries() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Initial management is to reduce caffeine and review triggers [1].",
        citations,
        strip_references=False,
        query="What initial management is appropriate for intermittent tremor?",
    )

    assert "initial management" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_scope_only_when_no_citations() -> None:
    answer, used = extract_citation_results(
        "Honest scope: the indexed passages do not cover this question.",
        [],
        strip_references=False,
    )

    assert "do not cover" in answer.lower()
    assert used == []


def test_extract_citation_results_strips_dangling_leading_connective() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "However, it emphasizes not delaying referral while awaiting results [1].",
        citations,
        strip_references=False,
    )

    assert answer.startswith("It emphasizes")
    assert used == [citations[0]]


def test_extract_citation_results_preserves_cited_scope_sentence() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "The indexed passages do not cover imaging guidance [1].",
        citations,
        strip_references=False,
    )

    assert "do not cover imaging guidance [1]" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_returns_empty_for_query_without_cited_support(
) -> None:
    answer, used = extract_citation_results(
        "Referral should be urgent.",
        [],
        strip_references=False,
        query="What referral pathway and urgency are recommended?",
    )

    assert answer == ""
    assert used == []


def test_extract_citation_results_keeps_answer_when_all_requested_parts_are_cited(
) -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        (
            "Baseline investigations include ESR and CRP [1]. "
            "Imaging should include X-ray [1]. "
            "Refer urgently via rheumatology pathway [1]."
        ),
        citations,
        strip_references=False,
        query=(
            "Patient with intermittent joint swelling. What baseline blood tests "
            "and imaging should be completed prior to referral?"
        ),
    )

    assert "do not directly cover" not in answer
    assert used == [citations[0]]


def test_extract_citation_results_keeps_uncited_low_risk_partial_answer() -> None:
    answer, used = extract_citation_results(
        "Baseline blood tests include ESR and CRP.",
        [],
        strip_references=False,
        query=(
            "35-year-old with intermittent joint swelling in knees and wrists "
            "over 4 months. CRP mildly raised. No clear diagnosis. What baseline "
            "blood tests and imaging should be completed prior to referral?"
        ),
        allow_uncited_answer=True,
    )

    assert "baseline blood tests include esr and crp" in answer.lower()
    assert used == []


def test_extract_citation_results_does_not_duplicate_existing_gap_sentence() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]
    sentence = (
        "The indexed passages retrieved do not directly cover the referral/urgency "
        "pathway part of this question."
    )

    answer, _ = extract_citation_results(
        f"Immediate investigations include urinalysis [1]. {sentence}",
        citations,
        strip_references=False,
        query=(
            "Patient with new proteinuria and rising creatinine. "
            "What immediate investigations and referral pathway are recommended?"
        ),
    )

    assert answer.count("do not directly cover") == 1


def test_extract_citation_results_drops_treatment_only_answer_when_not_requested() -> (
    None
):
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Start ACE inhibitors for proteinuria [1].",
        citations,
        strip_references=False,
        query=(
            "Patient with SLE and new proteinuria. "
            "What immediate investigations and referral pathway are recommended?"
        ),
    )

    assert answer == ""
    assert used == [citations[0]]


def test_has_cited_sentence_matching_skips_empty_units() -> None:
    assert (
        _has_cited_sentence_matching(
            "\n\nRefer urgently [1].",
            re.compile(r"\brefer\b", re.IGNORECASE),
        )
        is True
    )


def test_join_labels_handles_empty_and_two_labels() -> None:
    assert _join_labels([]) == ""
    assert _join_labels(["imaging", "referral"]) == "imaging and referral"


def test_enforce_partial_question_coverage_returns_empty_without_citations() -> None:
    assert (
        _enforce_partial_question_coverage(
            "Need referral guidance.",
            query="What referral pathway and urgency are recommended?",
            has_citations=False,
        )
        == ""
    )


def test_enforce_partial_question_coverage_keeps_uncited_allowed_answer() -> None:
    answer = _enforce_partial_question_coverage(
        "Baseline blood tests include ESR and CRP.",
        query=(
            "35-year-old with intermittent joint swelling in knees and wrists "
            "over 4 months. CRP mildly raised. No clear diagnosis. What baseline "
            "blood tests and imaging should be completed prior to referral?"
        ),
        has_citations=False,
        allow_uncited_answer=True,
    )

    assert "baseline blood tests include esr and crp" in answer.lower()


def test_enforce_partial_question_coverage_ignores_blank_focus_text() -> None:
    answer = _enforce_partial_question_coverage(
        "Baseline blood tests include ESR and CRP [1].",
        query=" \n\t ",
        has_citations=True,
    )

    assert "baseline blood tests include esr and crp" in answer.lower()


def test_enforce_partial_question_coverage_keeps_existing_gap_sentence() -> None:
    sentence = (
        "The indexed passages retrieved do not directly cover the referral/urgency "
        "pathway part of this question."
    )
    answer = _enforce_partial_question_coverage(
        f"Immediate investigations include urinalysis [1]. {sentence}",
        query=(
            "Patient with new proteinuria and rising creatinine. "
            "What immediate investigations and referral pathway are recommended?"
        ),
        has_citations=True,
    )

    assert answer.count("do not directly cover") == 1


def test_question_focus_text_prefers_last_question_sentence() -> None:
    focus = _question_focus_text(
        "CT head shows ventriculomegaly. Should normal pressure hydrocephalus "
        "be suspected and how urgently should this be referred?"
    )

    assert "ct head" not in focus.lower()
    assert "how urgently" in focus.lower()


def test_question_focus_text_handles_empty_inputs() -> None:
    assert _question_focus_text(None) == ""
    assert _question_focus_text(" \n\t ") == ""


def test_enforce_requested_scope_skips_blank_units() -> None:
    answer = _enforce_requested_scope(
        "\n\nStart ACE inhibitors.\n\n",
        query=(
            "Patient with SLE and new proteinuria. "
            "What immediate investigations and referral pathway are recommended?"
        ),
    )

    assert answer == ""


def test_enforce_requested_scope_keeps_treatment_for_ambiguous_management_queries() -> (
    None
):
    answer = _enforce_requested_scope(
        "PMR can be started on prednisolone in primary care [1].",
        query=(
            "Should polymyalgia rheumatica be started on steroids in primary care?"
        ),
    )

    assert "prednisolone" in answer.lower()

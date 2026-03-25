from __future__ import annotations

from src.api.citations import (
    extract_citation_results,
    has_query_overlap,
    parse_citation_group,
)
from src.api.schemas import SearchResult


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


def test_extract_citation_results_keeps_low_risk_uncited_context_in_balanced_mode() -> (
    None
):
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Refer urgently [1]. Consider extra hydration advice while waiting.",
        citations,
        strip_references=False,
    )

    assert answer == "Refer urgently [1]. Consider extra hydration advice while waiting."
    assert used == [citations[0]]


def test_extract_citation_results_normalizes_rule_style_citation_tokens() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Refer to neurology [1.4.4].",
        citations,
        strip_references=False,
    )

    assert answer == "Refer to neurology [1]."
    assert used == [citations[0]]


def test_extract_citation_results_keeps_scope_refusal_without_citations() -> None:
    answer, used = extract_citation_results(
        "Honest scope: The indexed passages do not cover investment advice.",
        [],
        strip_references=False,
    )

    assert "do not cover investment advice" in answer.lower()
    assert used == []


def test_extract_citation_results_strips_safety_leadin_phrase() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Regarding safety considerations, urgent referral is needed [1].",
        citations,
        strip_references=False,
    )

    assert "safety considerations" not in answer.lower()
    assert answer == "urgent referral is needed [1]."
    assert used == [citations[0]]


def test_extract_citation_results_adds_referral_gap_note_when_missing() -> None:
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


def test_extract_citation_results_returns_empty_with_no_referral_evidence() -> None:
    answer, used = extract_citation_results(
        "Referral should be urgent.",
        [],
        strip_references=False,
        query="What referral pathway and urgency are recommended?",
    )

    assert answer == ""
    assert used == []


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


def test_extract_citation_results_marks_missing_imaging_and_referral_parts() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Baseline blood tests include ESR and CRP [1].",
        citations,
        strip_references=False,
        query=(
            "Patient with intermittent joint swelling. What baseline blood tests "
            "and imaging should be completed prior to referral?"
        ),
    )

    assert "ESR and CRP [1]" in answer
    assert "imaging and referral/urgency pathway part of this question" in answer
    assert used == [citations[0]]


def test_extract_citation_results_drops_mmf_cyc_treatment_when_not_requested() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        (
            "Immediate investigations include urinalysis and creatinine [1]. "
            "Use mycophenolate mofetil (MMF) or cyclophosphamide (CYC) [1]."
        ),
        citations,
        strip_references=False,
        query=(
            "Patient with SLE and new proteinuria. "
            "What immediate investigations and referral pathway are recommended?"
        ),
    )

    assert "urinalysis and creatinine [1]" in answer.lower()
    assert "mycophenolate" not in answer.lower()
    assert "cyclophosphamide" not in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_drug_induced_diagnostic_exclusion_sentence() -> (
    None
):
    citations = [
        SearchResult(
            text=(
                "Other inflammatory rheumatic diseases, drug-induced myalgia, "
                "chronic pain syndromes, endocrine disease and neurological "
                "conditions reduce probability of PMR and should be excluded."
            ),
            source="S",
            score=0.9,
        )
    ]

    answer, used = extract_citation_results(
        (
            "Findings that reduce probability of PMR include drug-induced myalgia, "
            "endocrine disease and neurological conditions [1]."
        ),
        citations,
        strip_references=False,
        query=(
            "What findings reduce the probability of PMR and should prompt "
            "reconsidering diagnosis?"
        ),
    )

    assert "drug-induced myalgia" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_adds_supported_parts_from_used_citation() -> None:
    citations = [
        SearchResult(
            text=(
                "Offer rheumatoid factor testing. Consider anti-CCP if RF negative. "
                "X-ray the hands and feet. Refer urgently for persistent synovitis."
            ),
            source="S",
            score=0.9,
        )
    ]

    answer, used = extract_citation_results(
        "Offer a blood test for rheumatoid factor [1].",
        citations,
        strip_references=False,
        query=(
            "Patient with intermittent joint swelling. What baseline blood tests "
            "and imaging should be completed prior to referral?"
        ),
    )

    assert "blood test for rheumatoid factor [1]" in answer.lower()
    assert "imaging recommendations [1]" in answer.lower()
    assert "referral/urgency pathway recommendations [1]" in answer.lower()
    assert "do not directly cover" not in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_referring_phrase_counts_as_referral_coverage() -> (
    None
):
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        (
            "Before referring the patient, offer rheumatoid factor testing [1]. "
            "X-ray the hands and feet [1]."
        ),
        citations,
        strip_references=False,
        query=(
            "Patient with intermittent joint swelling. What baseline blood tests "
            "and imaging should be completed prior to referral?"
        ),
    )

    assert "referral/urgency pathway part of this question" not in answer
    assert "imaging part of this question" not in answer
    assert used == [citations[0]]


def test_extract_citation_results_keeps_treatment_when_requested() -> None:
    citations = [SearchResult(text="A", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Start ACE inhibitors for proteinuria [1].",
        citations,
        strip_references=False,
        query="What treatment is recommended for SLE proteinuria?",
    )

    assert "ACE inhibitors" in answer
    assert used == [citations[0]]


def test_extract_citation_results_keeps_treatment_when_query_asks_to_start() -> None:
    citations = [SearchResult(text="Start prednisolone 15 mg daily.", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "Start prednisolone 15 mg daily [1].",
        citations,
        strip_references=False,
        query="Should polymyalgia rheumatica be started on steroids in primary care?",
    )

    assert "prednisolone 15 mg daily [1]" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_acei_arb_when_query_mentions_acei_arb() -> None:
    citations = [
        SearchResult(
            text="ACEi/ARB are recommended for moderate proteinuria.",
            source="S",
            score=0.9,
        )
    ]

    answer, used = extract_citation_results(
        "Use ACE inhibitors or ARBs for moderate proteinuria [1].",
        citations,
        strip_references=False,
        query=(
            "In lupus nephritis with moderate proteinuria, what does guidance say "
            "about ACE inhibitor or ARB use?"
        ),
    )

    assert "ace inhibitors or arbs" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_supports_snippet_only_citation_shape() -> None:
    citation_like = type(
        "CitationLike",
        (),
        {
            "source": "S",
            "score": 0.9,
            "snippet": "Other inflammatory diseases reduce PMR probability.",
        },
    )

    answer, used = extract_citation_results(
        "Other inflammatory diseases reduce PMR probability [1].",
        [citation_like],
        strip_references=False,
        query="What findings reduce PMR probability?",
    )

    assert answer.endswith("[1].")
    assert len(used) == 1


def test_extract_citation_results_neutralizes_unsupported_rationale_clause() -> None:
    citations = [SearchResult(text="X-ray the hands and feet.", source="S", score=0.9)]

    answer, used = extract_citation_results(
        "X-ray the hands and feet [1] to assess erosive changes suggestive of RA.",
        citations,
        strip_references=False,
        query="What imaging should be completed prior to referral?",
    )

    assert "x-ray the hands and feet [1]" in answer.lower()
    assert "erosive changes" not in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_softens_cross_source_consensus_overclaim() -> None:
    citations = [
        SearchResult(text="Refer urgently.", source="S1", score=0.9),
        SearchResult(text="Referral is recommended.", source="S2", score=0.8),
    ]

    answer, used = extract_citation_results(
        "The referral urgency is explicitly stated in both guideline sections [1, 2].",
        citations,
        strip_references=False,
        query="What referral urgency is recommended?",
    )

    assert "explicitly stated in both guideline sections" not in answer.lower()
    assert "included in indexed passages [1, 2]" in answer.lower()
    assert used == citations


def test_extract_citation_results_drops_unsupported_timeframe_claim() -> None:
    citations = [
        SearchResult(
            text="Refer urgently for specialist assessment.",
            source="S",
            score=0.9,
        )
    ]

    answer, used = extract_citation_results(
        "Refer urgently within 24 hours [1]. Arrange specialist assessment [1].",
        citations,
        strip_references=False,
    )

    assert "within 24 hours" not in answer.lower()
    assert "arrange specialist assessment [1]" in answer.lower()
    assert used == [citations[0]]


def test_extract_citation_results_keeps_supported_timeframe_claim() -> None:
    citations = [
        SearchResult(
            text="Refer adults with persistent synovitis within 3 working days.",
            source="S",
            score=0.9,
        )
    ]

    answer, used = extract_citation_results(
        "Refer adults with persistent synovitis within 3 working days [1].",
        citations,
        strip_references=False,
    )

    assert "within 3 working days [1]" in answer.lower()
    assert used == [citations[0]]

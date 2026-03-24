from __future__ import annotations

from src.api.citations import (
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

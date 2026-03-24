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

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

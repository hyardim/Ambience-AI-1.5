from __future__ import annotations

import re
from typing import Any

from ..utils.citation_utils import (
    extract_citation_indices,
    parse_citation_group,
    rewrite_citations,
)
from .schemas import SearchResult

MAX_CITATIONS = 3
MIN_RELEVANCE = 0.25

GENERIC_TOKENS = {
    "guideline",
    "guidelines",
    "recommendation",
    "recommendations",
    "committee",
    "evidence",
    "information",
    "summary",
    "overview",
    "introduction",
    "statement",
    "data",
    "supplementary",
    "material",
    "details",
}

BOILERPLATE_PATTERNS = [
    "data availability",
    "supplementary material",
    "guideline committee",
    "finding more information",
    "evidence reviews",
    "copyright",
    "license",
    "doi",
    "manuscript",
]

# Re-export for existing consumers
__all__ = [
    "MAX_CITATIONS",
    "MIN_RELEVANCE",
    "extract_citation_indices",
    "extract_citation_results",
    "has_query_overlap",
    "is_boilerplate",
    "parse_citation_group",
    "rewrite_citations",
]


def has_query_overlap(question: str, chunk_text: str) -> bool:
    """Basic lexical check to ensure the chunk mentions query terms."""

    def _tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[A-Za-z0-9]+", text.lower())
            if len(token) >= 3 and token not in GENERIC_TOKENS
        }

    q_tokens = _tokens(question)
    c_tokens = _tokens(chunk_text)
    overlap = q_tokens.intersection(c_tokens)
    return bool(q_tokens and c_tokens and overlap)


def is_boilerplate(chunk: dict[str, Any]) -> bool:
    text = (chunk.get("text") or "").lower()
    section = (chunk.get("section_path") or "").lower()
    return any(
        pattern in text or pattern in section for pattern in BOILERPLATE_PATTERNS
    )


def extract_citation_results(
    answer_text: str,
    citations_retrieved: list[SearchResult],
    *,
    strip_references: bool,
) -> tuple[str, list[SearchResult]]:
    used_indices = extract_citation_indices(answer_text)
    sorted_used = sorted(
        index for index in used_indices if 1 <= index <= len(citations_retrieved)
    )
    citations_used = [citations_retrieved[index - 1] for index in sorted_used]
    renumber_map = {original: new for new, original in enumerate(sorted_used, start=1)}
    answer = rewrite_citations(answer_text, renumber_map)
    if strip_references:
        answer = re.sub(
            r"\n+\s*References?:.*",
            "",
            answer,
            flags=re.DOTALL | re.IGNORECASE,
        ).rstrip()
    return answer, citations_used

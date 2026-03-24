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
MIN_RELEVANCE = 0.05

_VALID_CITATION_GROUP_RE = re.compile(r"\[(?:\d+(?:\s*,\s*\d+)*)\]")
_RULE_STYLE_CITATION_RE = re.compile(r"\[(?:\d+(?:\.\d+)+)\]")
_SECTION_LABEL_RE = re.compile(
    r"\b(?:"
    r"General clinical context|"
    r"Safety (?:considerations|flags|net|flags/monitoring)|"
    r"Regarding safety considerations|"
    r"Regarding general clinical context"
    r")\b\s*[:,-]?\s*",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_CLINICAL_HINT_RE = re.compile(
    r"\b(refer|referral|urgent|stroke|tia|hydrocephalus|nph|gait|ataxia|weakness|"
    r"headache|jaw claudication|temporal arteritis|bell'?s palsy|migraine|"
    r"epilep\w*|monitor\w*|manage\w*|dose\w*|prednisolone|symptom\w*|"
    r"diagnos\w*|treat\w*|assessment|imaging|neurolog\w*|safety)\b",
    re.IGNORECASE,
)
_SCOPE_HINT_RE = re.compile(
    r"\b(honest scope|do not cover|does not cover|outside scope|cannot provide|"
    r"can't provide|cannot answer|insufficient evidence|not enough evidence)\b",
    re.IGNORECASE,
)

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


def _clean_answer_text(text: str) -> str:
    cleaned = _SECTION_LABEL_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _enforce_grounded_sentences(answer_text: str, *, has_citations: bool) -> str:
    """Drop uncited clinical claims from model output.

    Any sentence that appears clinical must include at least one valid [N]
    citation token to be retained. Scope/refusal sentences are kept when no
    citations are present.
    """
    units = [
        part.strip()
        for part in _SENTENCE_SPLIT_RE.split(answer_text)
        if part and part.strip()
    ]
    cited_units: list[str] = []
    scope_units: list[str] = []
    kept_units: list[str] = []

    for raw_unit in units:
        unit = _SECTION_LABEL_RE.sub("", raw_unit).strip(" -")
        unit = re.sub(r"^[*-]\s*", "", unit).strip()
        if not unit:
            continue

        has_valid_citation = bool(_VALID_CITATION_GROUP_RE.search(unit))
        if has_valid_citation:
            cited_units.append(unit)
            kept_units.append(unit)
            continue

        if _SCOPE_HINT_RE.search(unit):
            scope_units.append(unit)
            if not has_citations:
                kept_units.append(unit)
            continue

        if _CLINICAL_HINT_RE.search(unit):
            # Clinical statement without evidence marker: drop.
            continue

        if not has_citations:
            kept_units.append(unit)

    if has_citations and not kept_units and cited_units:
        kept_units = cited_units
    if not kept_units and scope_units:
        kept_units = scope_units[:1]

    return _clean_answer_text(" ".join(kept_units))


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
    # Strip guideline subsection references that look like citations
    # (e.g. [1.4.4]) to avoid treating them as evidence markers.
    answer = _RULE_STYLE_CITATION_RE.sub("", answer)
    answer = _clean_answer_text(answer)
    answer = _enforce_grounded_sentences(answer, has_citations=bool(citations_used))
    return answer, citations_used

from __future__ import annotations

import re
from typing import Any

from ..retrieval.relevance import has_query_overlap, query_overlap_count
from ..utils.citation_utils import (
    extract_citation_indices,
    parse_citation_group,
    rewrite_citations,
)
from .schemas import SearchResult

MAX_CITATIONS = 5
MIN_RELEVANCE = 0.12
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
_REFERRAL_QUERY_HINT_RE = re.compile(
    r"\b(refer|referral|pathway|urgent|immediate|urgency|how urgently)\b",
    re.IGNORECASE,
)
_REFERRAL_SENTENCE_HINT_RE = re.compile(
    r"\b(refer|referral|pathway|urgent|urgency)\b",
    re.IGNORECASE,
)
_INVESTIGATION_QUERY_HINT_RE = re.compile(
    r"\b(investigations?|investigate|baseline|blood tests?|work[- ]?up|"
    r"laboratory|labs?)\b",
    re.IGNORECASE,
)
_INVESTIGATION_SENTENCE_HINT_RE = re.compile(
    r"\b(investigations?|blood tests?|fbc|cbc|esr|crp|urinalysis|"
    r"anti-?ccp|rheumatoid factor|rf\b|ana|dsdna|u&es|egfr|creatinine)\b",
    re.IGNORECASE,
)
_IMAGING_QUERY_HINT_RE = re.compile(
    r"\b(imaging|x-?ray|ultrasound|mri|ct|scan)\b",
    re.IGNORECASE,
)
_IMAGING_SENTENCE_HINT_RE = re.compile(
    r"\b(x-?ray|ultrasound|mri|ct|scan|imaging)\b",
    re.IGNORECASE,
)
_TREATMENT_QUERY_HINT_RE = re.compile(
    r"\b(treat\w*|management|manage\w*|therapy|medication|dose|prescrib\w*|drug)\b",
    re.IGNORECASE,
)
_TREATMENT_SENTENCE_HINT_RE = re.compile(
    r"\b(ace inhibitors?|acei|arb|angiotensin|prednisolone|steroid|"
    r"immunosuppress\w*|treat\w*|management|manage\w*|therapy|medication|"
    r"dose|prescrib\w*|drug)\b",
    re.IGNORECASE,
)

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
    "thank you for this referral",
    "we have not offered an appointment",
    "we have not made an appointment",
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
    "query_overlap_count",
    "rewrite_citations",
]


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
            continue

        if not has_citations:
            kept_units.append(unit)

    return _clean_answer_text(" ".join(kept_units))


def _has_cited_sentence_matching(
    answer_text: str,
    sentence_pattern: re.Pattern[str],
) -> bool:
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue
        if _VALID_CITATION_GROUP_RE.search(unit) and sentence_pattern.search(unit):
            return True
    return False


def _join_labels(labels: list[str]) -> str:
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


def _enforce_partial_question_coverage(
    answer_text: str,
    *,
    query: str | None,
    has_citations: bool,
) -> str:
    if not answer_text.strip() or not query:
        return answer_text

    requested_parts: list[tuple[str, re.Pattern[str]]] = []
    if _INVESTIGATION_QUERY_HINT_RE.search(query):
        requested_parts.append(("investigations", _INVESTIGATION_SENTENCE_HINT_RE))
    if _IMAGING_QUERY_HINT_RE.search(query):
        requested_parts.append(("imaging", _IMAGING_SENTENCE_HINT_RE))
    if _REFERRAL_QUERY_HINT_RE.search(query):
        requested_parts.append(("referral/urgency pathway", _REFERRAL_SENTENCE_HINT_RE))

    if not requested_parts:
        return answer_text
    if not has_citations:
        return ""

    missing_parts = [
        label
        for label, pattern in requested_parts
        if not _has_cited_sentence_matching(answer_text, pattern)
    ]
    if not missing_parts:
        return answer_text

    gap_sentence = (
        "The indexed passages retrieved do not directly cover the "
        f"{_join_labels(missing_parts)} part of this question."
    )
    if gap_sentence.lower() in answer_text.lower():
        return answer_text
    return _clean_answer_text(f"{answer_text} {gap_sentence}")


def _enforce_requested_scope(answer_text: str, *, query: str | None) -> str:
    if not answer_text.strip():
        return ""
    if not query or _TREATMENT_QUERY_HINT_RE.search(query):
        return answer_text

    kept_units: list[str] = []
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue
        if _TREATMENT_SENTENCE_HINT_RE.search(unit):
            continue
        kept_units.append(unit)

    return _clean_answer_text(" ".join(kept_units))


def extract_citation_results(
    answer_text: str,
    citations_retrieved: list[SearchResult],
    *,
    strip_references: bool,
    query: str | None = None,
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
    answer = _RULE_STYLE_CITATION_RE.sub("", answer)
    answer = _clean_answer_text(answer)
    answer = _enforce_grounded_sentences(answer, has_citations=bool(citations_used))
    answer = _enforce_requested_scope(answer, query=query)
    answer = _enforce_partial_question_coverage(
        answer,
        query=query,
        has_citations=bool(citations_used),
    )
    return answer, citations_used

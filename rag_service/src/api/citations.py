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
# Matches year/amendment metadata inside citation brackets:
# [1, 2009] → [1]    [1, 2009; amended 2018] → [1]    [1; amended 2018] → [1]
_YEAR_CITATION_CLEANUP_RE = re.compile(
    r"\[(\d+(?:\s*,\s*\d+)*)"           # leading valid indices
    r"(?:\s*[,;]\s*(?:\d{4}|amended?)[^]]*)"  # trailing year/amendment junk
    r"\]",
    re.IGNORECASE,
)
# Matches recommendation numbers mixed into citation brackets:
# [1, 1.1.2] → [1]    [1, 1.1.3] → [1]    [2, 1.1.4] → [2]
_REC_IN_CITATION_CLEANUP_RE = re.compile(
    r"\[(\d+)"                           # leading valid index
    r"(?:\s*,\s*\d+(?:\.\d+)+)+"         # one or more ", 1.1.2" rec-number parts
    r"\]",
)
# Strip inline recommendation-number references the model echoes from guideline text.
# e.g. "as per recommendation 1.1.1" or "recommendation 1.1.2 on page 6"
_REC_NUMBER_INLINE_RE = re.compile(
    r",?\s*(?:as per |following (?:guidance from )?|in |per )"
    r"recommendation\s+\d+(?:\.\d+)+"
    r"(?:\s+on\s+page\s+\d+(?:\s+of\s+the\s+indexed\s+guideline\s+passage)?)?",
    re.IGNORECASE,
)
_PAREN_SECTION_REFERENCE_RE = re.compile(
    r"\(\s*(\[(?:\d+(?:\s*,\s*\d+)*)\])\s*(?:section\s*)?\d+(?:\.\d+)+\s*\)",
    re.IGNORECASE,
)
_POST_CITATION_SECTION_REFERENCE_RE = re.compile(
    r"(\[(?:\d+(?:\s*,\s*\d+)*)\])\s*(?:section\s*)?\d+(?:\.\d+)+\b",
    re.IGNORECASE,
)
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
_LEADING_CONNECTIVE_RE = re.compile(
    r"^(?:however|but|also|additionally|furthermore|moreover|in addition)\s*,?\s+",
    re.IGNORECASE,
)
_LEADING_PAGE_LABEL_RE = re.compile(
    r"^(?:\[(?:\d+(?:\s*,\s*\d+)*)\]\s*)?page\s+\d+\s+",
    re.IGNORECASE,
)
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
    r"\b(refer\w*|pathway|urgent\w*|immediate|urgency|how urgently)\b",
    re.IGNORECASE,
)
_REFERRAL_SENTENCE_HINT_RE = re.compile(
    r"\b(refer\w*|pathway|urgent\w*|urgency)\b",
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
    r"\b("
    r"treat\w*|management|manage\w*|therapy|medication|dose|prescrib\w*|drug|"
    r"start\w*|initiat\w*|commenc\w*|begin\w*|stop\w*|withhold\w*|continue\w*|"
    r"first[- ]line|initial management|prednisolone|steroid\w*"
    r")\b",
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
    cleaned = _PAREN_SECTION_REFERENCE_RE.sub(r"\1", cleaned)
    cleaned = _POST_CITATION_SECTION_REFERENCE_RE.sub(r"\1", cleaned)
    # Strip year/amendment metadata from citations: [1, 2009; amended 2018] → [1]
    cleaned = _YEAR_CITATION_CLEANUP_RE.sub(r"[\1]", cleaned)
    # Strip recommendation numbers from citation brackets: [1, 1.1.2] → [1]
    cleaned = _REC_IN_CITATION_CLEANUP_RE.sub(r"[\1]", cleaned)
    # Strip echoed recommendation numbers: "as per recommendation 1.1.1 on page 6"
    cleaned = _REC_NUMBER_INLINE_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = _LEADING_PAGE_LABEL_RE.sub("", cleaned)
    cleaned = _LEADING_CONNECTIVE_RE.sub("", cleaned)
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _question_focus_text(query: str | None) -> str:
    if not query:
        return ""
    units = [
        part.strip()
        for part in _SENTENCE_SPLIT_RE.split(query)
        if part and part.strip()
    ]
    if not units:
        return ""
    question_units = [unit for unit in units if "?" in unit]
    if question_units:
        return question_units[-1]
    return units[-1]


def _enforce_grounded_sentences(answer_text: str, *, has_citations: bool) -> str:
    """Clean up the answer text.

    Previously this function dropped any uncited sentence containing clinical
    keywords, which was too aggressive — it silently removed accurate bridging
    sentences and produced vague meta-references instead of real answers.

    Now it only:
    - Strips section-label artefacts from each sentence.
    - Suppresses "honest scope" disclaimer sentences when the answer already
      has citations (the disclaimer is redundant and confusing in that case).
    - Preserves every other sentence — cited or not — so the model can
      synthesise coherent answers using both indexed passages and general
      clinical knowledge.
    """
    units = [
        part.strip()
        for part in _SENTENCE_SPLIT_RE.split(answer_text)
        if part and part.strip()
    ]
    kept_units: list[str] = []

    for raw_unit in units:
        unit = _SECTION_LABEL_RE.sub("", raw_unit).strip(" -")
        unit = re.sub(r"^[*-]\s*", "", unit).strip()
        if not unit:
            continue

        # Drop "honest scope" disclaimers only when citations are present —
        # they are redundant and undermine an otherwise useful answer.
        if has_citations and _SCOPE_HINT_RE.search(unit):
            continue

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
    allow_uncited_answer: bool = False,
) -> str:
    if not answer_text.strip() or not query:
        return answer_text

    focus_text = _question_focus_text(query)
    if not focus_text:
        return answer_text

    requested_parts: list[tuple[str, re.Pattern[str]]] = []
    if _INVESTIGATION_QUERY_HINT_RE.search(focus_text):
        requested_parts.append(("investigations", _INVESTIGATION_SENTENCE_HINT_RE))
    if _IMAGING_QUERY_HINT_RE.search(focus_text):
        requested_parts.append(("imaging", _IMAGING_SENTENCE_HINT_RE))
    if _REFERRAL_QUERY_HINT_RE.search(focus_text):
        requested_parts.append(("referral/urgency pathway", _REFERRAL_SENTENCE_HINT_RE))

    if not requested_parts:
        return answer_text
    if not has_citations:
        return answer_text if allow_uncited_answer else ""

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
    if not query:
        return answer_text

    query_lc = query.lower()
    requests_treatment = bool(_TREATMENT_QUERY_HINT_RE.search(query_lc))
    requests_non_treatment_only = any(
        pattern.search(query_lc)
        for pattern in (
            _INVESTIGATION_QUERY_HINT_RE,
            _IMAGING_QUERY_HINT_RE,
            _REFERRAL_QUERY_HINT_RE,
        )
    )
    if requests_treatment or not requests_non_treatment_only:
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
    allow_uncited_answer: bool = False,
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
        allow_uncited_answer=allow_uncited_answer,
    )
    return answer, citations_used

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
_RULE_STYLE_CITATION_RE = re.compile(r"\[(\d+)(?:\.\d+)+\]")
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
    r"\b(refer\w*|referr\w*|pathway|urgent|immediate|urgency|how urgently)\b",
    re.IGNORECASE,
)
_REFERRAL_SENTENCE_HINT_RE = re.compile(
    r"\b(refer\w*|referr\w*|pathway|urgent|urgency)\b",
    re.IGNORECASE,
)
_INVESTIGATION_QUERY_HINT_RE = re.compile(
    r"\b(investigations?|investigate|baseline|blood tests?|work[- ]?up|"
    r"laboratory|labs?)\b",
    re.IGNORECASE,
)
_INVESTIGATION_SENTENCE_HINT_RE = re.compile(
    r"\b(investigations?|blood tests?|fbc|cbc|esr|crp|urinalysis|"
    r"anti-?ccp|rheumatoid factor|rf\b|ana|dsdna|u&es|eGFR|creatinine)\b",
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
    r"immunosuppress\w*|mycophenolate|mmf\b|cyclophosphamide|cyc\b|"
    r"treat\w*|management|manage\w*|therapy|medication|"
    r"dose|prescrib\w*|drug)\b",
    re.IGNORECASE,
)
_TIME_VALUE_RE = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty[- ]four)"
_EXPLICIT_TIMEFRAME_RE = re.compile(
    rf"\b(?:within\s+{_TIME_VALUE_RE}\s+"
    rf"(?:minute|minutes|hour|hours|day|days|week|weeks|working day|working days)"
    rf"|{_TIME_VALUE_RE}\s+working\s+days?|same[- ]day|next[- ]day)\b",
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
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_rule_style_citations(answer_text: str, citation_count: int) -> str:
    """Map guideline subsection markers like [1.1.4] to source-style [1]."""

    def _replace(match: re.Match[str]) -> str:
        candidate = int(match.group(1))
        if 1 <= candidate <= citation_count:
            return f"[{candidate}]"
        return ""

    return _RULE_STYLE_CITATION_RE.sub(_replace, answer_text)


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


def _normalize_text_for_match(text: str) -> str:
    normalized = text.lower().replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _citation_indices_for_unit(unit: str) -> set[int]:
    indices: set[int] = set()
    for group in _VALID_CITATION_GROUP_RE.findall(unit):
        indices.update(parse_citation_group(group[1:-1]))
    return indices


def _enforce_explicit_timeframe_grounding(
    answer_text: str,
    citations_used: list[SearchResult],
) -> str:
    """Drop explicit timeframe claims unless the phrase appears in cited evidence."""
    if not answer_text.strip():
        return ""
    if not citations_used:
        return answer_text

    citation_text_by_index = {
        idx: _normalize_text_for_match(citation.text)
        for idx, citation in enumerate(citations_used, start=1)
    }
    kept_units: list[str] = []
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue

        timeframe_matches = _EXPLICIT_TIMEFRAME_RE.findall(unit)
        if not timeframe_matches:
            kept_units.append(unit)
            continue

        cited_indices = _citation_indices_for_unit(unit)
        if not cited_indices:
            kept_units.append(unit)
            continue

        citation_haystack = " ".join(
            citation_text_by_index[index]
            for index in sorted(cited_indices)
            if index in citation_text_by_index
        )
        keep_unit = True
        for phrase in timeframe_matches:
            normalized_phrase = _normalize_text_for_match(phrase)
            if normalized_phrase and normalized_phrase not in citation_haystack:
                keep_unit = False
                break

        if keep_unit:
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


def _find_supporting_citation_index(
    citations_used: list[SearchResult],
    pattern: re.Pattern[str],
) -> int | None:
    for idx, citation in enumerate(citations_used, start=1):
        if pattern.search(citation.text):
            return idx
    return None


def _enforce_partial_question_coverage(
    answer_text: str,
    *,
    query: str | None,
    has_citations: bool,
    citations_used: list[SearchResult],
) -> str:
    """Append explicit coverage gaps for unsupported multi-part asks.

    For multipart asks (investigations, imaging, referral/urgency), keep cited
    supported statements and append a scoped "not covered" note for missing
    parts instead of allowing fabricated completion.
    """
    if not answer_text.strip():
        return ""
    if not query:
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

    additions: list[str] = []
    missing_parts: list[str] = []
    for label, pattern in requested_parts:
        if _has_cited_sentence_matching(answer_text, pattern):
            continue

        supporting_index = _find_supporting_citation_index(citations_used, pattern)
        if supporting_index is not None:
            additions.append(
                "The indexed passages also include "
                f"{label} recommendations [{supporting_index}]."
            )
        else:
            missing_parts.append(label)

    if additions:
        answer_text = _clean_answer_text(f"{answer_text} {' '.join(additions)}")

    if not missing_parts:
        return answer_text

    missing_phrase = _join_labels(missing_parts)
    gap_sentence = (
        "The indexed passages retrieved do not directly cover the "
        f"{missing_phrase} part of this question."
    )
    if gap_sentence.lower() in answer_text.lower():
        return answer_text

    return _clean_answer_text(
        f"{answer_text} {gap_sentence}"
    )


def _enforce_requested_scope(answer_text: str, *, query: str | None) -> str:
    """Remove treatment-only guidance when treatment was not requested."""
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
    answer_text = _normalize_rule_style_citations(
        answer_text,
        citation_count=len(citations_retrieved),
    )
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
    answer = _clean_answer_text(answer)
    answer = _enforce_grounded_sentences(answer, has_citations=bool(citations_used))
    answer = _enforce_explicit_timeframe_grounding(answer, citations_used)
    answer = _enforce_requested_scope(answer, query=query)
    answer = _enforce_partial_question_coverage(
        answer,
        query=query,
        has_citations=bool(citations_used),
        citations_used=citations_used,
    )
    return answer, citations_used

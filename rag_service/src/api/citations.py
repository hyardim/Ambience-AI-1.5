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
# Handles all common phrasings:
#   "as per recommendation 1.1.1"
#   "as per guideline recommendation 1.1.1"
#   "as outlined in recommendation 1.1.2"
#   "following guidance from recommendation 1.1.3"
#   "(recommendation 1.1.3)"
#   "following guideline amendment in 2018"
_REC_NUMBER_INLINE_RE = re.compile(
    r",?\s*(?:as per |following (?:guidance from )?|as outlined in |as stated in |in |per )"
    r"(?:guideline\s+)?"          # optional "guideline" word between preposition and "recommendation"
    r"recommendation\s+\d+(?:\.\d+)+"
    r"(?:\s+on\s+page\s+\d+(?:\s+of\s+the\s+indexed\s+guideline\s+passage)?)?",
    re.IGNORECASE,
)
# Standalone parenthetical recommendation number, with or without trailing citation:
# "(recommendation 1.1.3)"  →  ""
# "(recommendation 1.1.3 [1])"  →  ""
_PAREN_REC_NUMBER_RE = re.compile(
    r"\(\s*recommendation\s+\d+(?:\.\d+)+\s*(?:\[[\d,\s]+\])?\s*\)",
    re.IGNORECASE,
)
# Catch bare "recommendation X.X.X" anywhere it appears (with or without trailing [N]):
# "recommendation 1.1.4 [1] advises..." → strips "recommendation 1.1.4 [1]"
# This is a superset of _REC_NUMBER_INLINE_RE for cases with no preceding phrase.
_REC_NUMBER_BARE_RE = re.compile(
    r",?\s*\brecommendation\s+\d+(?:\.\d+)+\s*(?:\[[\d,\s]+\])?",
    re.IGNORECASE,
)
# Guideline amendment year reference: "following guideline amendment in 2018"
_GUIDELINE_AMENDMENT_RE = re.compile(
    r",?\s*following\s+guideline\s+amendment\s+in\s+\d{4}",
    re.IGNORECASE,
)
# Standalone dotted numbers that look like recommendation references:
# "(1.15.4)" → ""    "1.15.2" at sentence boundary → ""
_STANDALONE_DOTTED_NUMBER_RE = re.compile(
    r"\(\s*\d+(?:\.\d+){2,}\s*\)",  # parenthesised: (1.15.4)
)
# Fabricated external guideline references the model hallucinates:
# "(AAN/AES, 2015)" → ""   "(NICE, 2020 [1])" → ""   "(BSR, 2010)" → kept (valid)
# Only strip when they include a year AND an organisation not from our sources
_FABRICATED_REF_RE = re.compile(
    r"\(\s*(?:AAN|AES|AAN/AES|ACR|EULAR|WHO|BMA|RCP|SIGN|"
    r"American Academy|American Epilepsy|European League)"
    r"[^)]{0,40}\d{4}[^)]{0,20}\)",
    re.IGNORECASE,
)
# Strip leaked prompt-rule references the model echoes:
#   "(rule 11)"  "as per rule 11"  "Note: ... (rule 11)."
#   "...is not appropriate for this presentation (rule 11)"
_LEAKED_RULE_REF_RE = re.compile(
    r"\s*\(rule\s+\d+\)\.?",
    re.IGNORECASE,
)
# Meta-commentary about context passages or prompt instructions:
#   "as described in the context passage related to stroke"
#   "regardless of what the retrieved context passages say"
_META_CONTEXT_RE = re.compile(
    r",?\s*as described in the context passage[^.]*",
    re.IGNORECASE,
)
_META_CONTEXT_REGARDLESS_RE = re.compile(
    r"\s*regardless of what the retrieved context passages say\.?",
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
# Strip orphaned leading citation that opens a sentence: "[1], primary care should..."
_LEADING_CITATION_COMMA_RE = re.compile(
    r"^\[(?:\d+(?:\s*,\s*\d+)*)\]\s*,\s*",
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
    r"\b(x-?ray\w*|ultrasound|mri|ct\b|scan\w*|imaging)\b",
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
    r"\b(ace inhibitors?|acei|arb|angiotensin|prednisolone|methotrexate|"
    r"hydroxychloroquine|sulfasalazine|leflunomide|dmard|biologic\w*|"
    r"immunosuppress\w*|steroid\w*|prescrib\w*|dose\s+of|mg\b|start\s+\w+\s+at)\b",
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
    # Strip parenthetical rec numbers: "(recommendation 1.1.3)"
    cleaned = _PAREN_REC_NUMBER_RE.sub("", cleaned)
    # Strip guideline amendment year refs: "following guideline amendment in 2018"
    cleaned = _GUIDELINE_AMENDMENT_RE.sub("", cleaned)
    # Strip any remaining bare "recommendation X.X.X [N]" references not caught above
    cleaned = _REC_NUMBER_BARE_RE.sub("", cleaned)
    # Strip standalone dotted numbers in parens: (1.15.4)
    cleaned = _STANDALONE_DOTTED_NUMBER_RE.sub("", cleaned)
    # Strip fabricated external guideline references: (AAN/AES, 2015)
    cleaned = _FABRICATED_REF_RE.sub("", cleaned)
    # Strip leaked prompt-rule references: "(rule 11)", "as per rule 11"
    cleaned = _LEAKED_RULE_REF_RE.sub("", cleaned)
    # Strip meta-commentary about context passages
    cleaned = _META_CONTEXT_RE.sub("", cleaned)
    cleaned = _META_CONTEXT_REGARDLESS_RE.sub(".", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = _LEADING_PAGE_LABEL_RE.sub("", cleaned)
    # Strip orphaned leading citations: "[1], primary care should..." → "Primary care should..."
    cleaned = _LEADING_CITATION_COMMA_RE.sub("", cleaned)
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
    """Light cleanup pass over the answer text.

    Only strips scope-disclaimer sentences when the answer already has
    citations (they are redundant and undermine an otherwise useful answer).
    All other sentences are preserved — the LLM at low temperature with a
    grounded prompt is already well-constrained.
    """
    if not has_citations:
        return answer_text

    units = [
        part.strip()
        for part in _SENTENCE_SPLIT_RE.split(answer_text)
        if part and part.strip()
    ]
    kept_units: list[str] = []

    for raw_unit in units:
        unit = raw_unit.strip()
        if not unit:
            continue
        if _SCOPE_HINT_RE.search(unit):
            continue
        kept_units.append(unit)

    return " ".join(kept_units)


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
    """No-op — previously appended false coverage disclaimers.

    The LLM handles partial coverage naturally via its prompt instructions.
    Kept as a function signature for API compatibility.
    """
    return answer_text


def _enforce_requested_scope(answer_text: str, *, query: str | None) -> str:
    """No-op — previously stripped treatment sentences from non-treatment queries.

    This was too aggressive and removed clinically relevant content (e.g.
    mentioning prednisolone dose when asked about PMR management).
    Kept as a function signature for API compatibility.
    """
    if not answer_text.strip():
        return ""
    return answer_text


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
    # Strip summary/recap tail paragraphs the model adds despite the prompt rule
    answer = re.sub(
        r"\n+\s*(?:In summary|To summarise|To summarize|In conclusion)[,:].*",
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

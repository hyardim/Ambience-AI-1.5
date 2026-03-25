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
_HIGH_RISK_UNCITED_CLAIM_RE = re.compile(
    r"\b(refer\w*|referr\w*|urgent|immediate|start\w*|initiat\w*|"
    r"commenc\w*|begin\w*|prescrib\w*|dose\w*|treat\w*|therapy|"
    r"medication|steroid\w*|acei|arb|insulin|admit\w*|biopsy)\b",
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
    r"\b(treat\w*|management|manage\w*|therapy|medication|dose|prescrib\w*|drug|"
    r"start\w*|initiat\w*|commenc\w*|begin\w*|steroid\w*|prednisolone|"
    r"ace inhibitors?|acei|arb|angiotensin|insulin)\b",
    re.IGNORECASE,
)
_TREATMENT_SENTENCE_HINT_RE = re.compile(
    r"\b(ace inhibitors?|acei|arb|angiotensin|prednisolone|steroid|"
    r"immunosuppress\w*|mycophenolate|mmf\b|cyclophosphamide|cyc\b|"
    r"treat\w*|management|manage\w*|therapy|medication|"
    r"dose|prescrib\w*)\b",
    re.IGNORECASE,
)
_ADDITIONAL_BRANCH_PREFIX_RE = re.compile(
    r"^(?:additionally|also|furthermore|moreover)\b",
    re.IGNORECASE,
)
_ADULT_QUERY_HINT_RE = re.compile(
    r"\b(adult|adults|older adult|older adults|over\s*\d{1,2}s?)\b",
    re.IGNORECASE,
)
_CHILD_POPULATION_HINT_RE = re.compile(
    r"\b(child|children|young people|paediatric|pediatric|under\s*\d+)\b",
    re.IGNORECASE,
)
_ADULT_POPULATION_HINT_RE = re.compile(r"\badult(?:s)?\b", re.IGNORECASE)
_TIME_VALUE_RE = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty[- ]four)"
_EXPLICIT_TIMEFRAME_RE = re.compile(
    rf"\b(?:within\s+{_TIME_VALUE_RE}\s+"
    rf"(?:minute|minutes|hour|hours|day|days|week|weeks|working day|working days)"
    rf"|{_TIME_VALUE_RE}\s+working\s+days?|same[- ]day|next[- ]day)\b",
    re.IGNORECASE,
)
_RATIONALE_MARKER_RE = re.compile(
    r"\b(because|therefore|thus|to assess|to evaluate|to identify|"
    r"suggestive of|indicating|which suggests?|which indicates?)\b",
    re.IGNORECASE,
)
_DIRECTIVE_SECTION_HINT_RE = re.compile(
    r"\b(recommendation|recommendations|referral|pathway|when to refer|"
    r"management|treatment|diagnosis)\b",
    re.IGNORECASE,
)
_NON_DIRECTIVE_SECTION_HINT_RE = re.compile(
    r"\b(discussion|results|context|background|rationale|headlines|"
    r"rigor of development|why the committee made)\b",
    re.IGNORECASE,
)
_HIGH_RISK_REFERRAL_ACTION_RE = re.compile(
    r"\b(refer\w*|referr\w*|pathway|urgent|immediate|urgency)\b",
    re.IGNORECASE,
)
_HIGH_RISK_TREATMENT_ACTION_RE = re.compile(
    r"\b(start\w*|initiat\w*|commenc\w*|begin\w*|prescrib\w*|dose\w*|"
    r"steroid\w*|therapy|medication)\b",
    re.IGNORECASE,
)
_HIGH_RISK_BIOPSY_ACTION_RE = re.compile(r"\bbiopsy\b", re.IGNORECASE)
_CROSS_SOURCE_OVERCLAIM_RE = re.compile(
    r"\b(?:explicitly|clearly)\s+stated\s+in\s+both\s+"
    r"(?:guideline\s+)?(?:sections?|sources?|passages?)\b",
    re.IGNORECASE,
)
_CROSS_SOURCE_SOFTEN_RE = re.compile(
    r"\bin\s+both\s+(?:guideline\s+)?(?:sections?|sources?|passages?)\b",
    re.IGNORECASE,
)
_RATIONALE_STOPWORDS = {
    "and",
    "the",
    "that",
    "with",
    "from",
    "for",
    "this",
    "these",
    "those",
    "therefore",
    "because",
    "thus",
    "which",
    "suggests",
    "indicates",
    "assess",
    "evaluate",
    "identify",
    "help",
    "helps",
}

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


def _enforce_grounded_sentences(
    answer_text: str,
    *,
    has_citations: bool,
) -> str:
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
            # Keep low-risk connective clinical context when at least one
            # grounded citation exists; still block high-risk uncited advice.
            if has_citations and not _HIGH_RISK_UNCITED_CLAIM_RE.search(unit):
                kept_units.append(unit)
                continue
            continue

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


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(token) >= 4 and token not in _RATIONALE_STOPWORDS
    }


def _citation_indices_for_unit(unit: str) -> set[int]:
    indices: set[int] = set()
    for group in _VALID_CITATION_GROUP_RE.findall(unit):
        indices.update(parse_citation_group(group[1:-1]))
    return indices


def _citation_text(citation: Any) -> str:
    """Best-effort access to citation text across SearchResult-like shapes."""
    if hasattr(citation, "text"):
        value = getattr(citation, "text")
        if isinstance(value, str):
            return value
    if hasattr(citation, "snippet"):
        value = getattr(citation, "snippet")
        if isinstance(value, str):
            return value
    if isinstance(citation, dict):
        text_value = citation.get("text") or citation.get("snippet")
        if isinstance(text_value, str):
            return text_value
    return ""


def _citation_section_path(citation: Any) -> str:
    if hasattr(citation, "section_path"):
        value = getattr(citation, "section_path")
        if isinstance(value, str):
            return value
    if isinstance(citation, dict):
        value = citation.get("section_path")
        if isinstance(value, str):
            return value
    return ""


def _is_directive_citation(citation: Any) -> bool:
    section_path = _citation_section_path(citation)
    if _DIRECTIVE_SECTION_HINT_RE.search(section_path):
        return True
    if _NON_DIRECTIVE_SECTION_HINT_RE.search(section_path):
        return False

    citation_text = _citation_text(citation)
    if not citation_text:
        return False
    has_recommendation_marker = bool(re.search(r"\b\d+\.\d+(?:\.\d+)?\b", citation_text))
    has_directive_verb = bool(
        re.search(
            r"\b(refer\w*|offer|consider|start\w*|initiat\w*|prescrib\w*|biopsy|urgent|immediate)\b",
            citation_text,
            re.IGNORECASE,
        )
    )
    if has_recommendation_marker and has_directive_verb:
        return True
    return has_directive_verb and len(citation_text) >= 24


def _citation_has_low_signal(citation: Any) -> bool:
    section_path = _citation_section_path(citation).strip()
    citation_text = _citation_text(citation).strip()
    return not section_path and len(citation_text) < 24


def _high_risk_action_type(unit: str) -> str | None:
    if _HIGH_RISK_BIOPSY_ACTION_RE.search(unit):
        return "biopsy"
    if _HIGH_RISK_TREATMENT_ACTION_RE.search(unit):
        return "treatment"
    if _HIGH_RISK_REFERRAL_ACTION_RE.search(unit):
        return "referral"
    return None


def _format_citation_group(indices: set[int]) -> str:
    ordered = sorted(index for index in indices if index >= 1)
    if not ordered:
        return "[1]"
    return "[" + ", ".join(str(index) for index in ordered) + "]"


def _high_risk_gap_sentence(action_type: str, citation_group: str) -> str:
    if action_type == "referral":
        return (
            "The indexed passages include relevant context "
            f"{citation_group}, but do not provide a directive recommendation "
            "on referral urgency in the cited sections."
        )
    if action_type == "biopsy":
        return (
            "The indexed passages include relevant context "
            f"{citation_group}, but do not provide a directive recommendation "
            "to perform biopsy in the cited sections."
        )
    return (
        "The indexed passages include relevant context "
        f"{citation_group}, but do not provide a directive recommendation "
        "to start or prescribe treatment in the cited sections."
    )


def _ensure_citation_in_unit(unit: str, source_unit: str) -> str:
    if _VALID_CITATION_GROUP_RE.search(unit):
        return unit
    first_group = _VALID_CITATION_GROUP_RE.search(source_unit)
    if not first_group:
        return unit
    return f"{unit} {first_group.group(0)}".strip()


def _neutralize_unsupported_rationale_clauses(
    answer_text: str,
    citations_used: list[SearchResult],
) -> str:
    """Keep cited recommendation sentences but trim unsupported rationale tails."""
    if not answer_text.strip() or not citations_used:
        return answer_text

    citation_haystack_tokens_by_index = {
        idx: _content_tokens(_citation_text(citation))
        for idx, citation in enumerate(citations_used, start=1)
    }
    kept_units: list[str] = []
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue

        cited_indices = _citation_indices_for_unit(unit)
        if not cited_indices:
            kept_units.append(unit)
            continue

        marker = _RATIONALE_MARKER_RE.search(unit)
        if not marker:
            kept_units.append(unit)
            continue

        rationale_tokens = _content_tokens(unit[marker.start() :])
        if not rationale_tokens:
            kept_units.append(unit)
            continue

        cited_tokens: set[str] = set()
        for index in cited_indices:
            cited_tokens.update(citation_haystack_tokens_by_index.get(index, set()))
        overlap = rationale_tokens.intersection(cited_tokens)
        overlap_ratio = len(overlap) / max(len(rationale_tokens), 1)
        if overlap_ratio >= 0.15:
            kept_units.append(unit)
            continue

        trimmed = unit[: marker.start()].rstrip(" ,;:-")
        trimmed = _ensure_citation_in_unit(trimmed, unit)
        if trimmed and trimmed[-1] not in ".!?":
            trimmed = f"{trimmed}."
        if trimmed:
            kept_units.append(trimmed)

    return _clean_answer_text(" ".join(kept_units))


def _enforce_high_risk_action_source_quality(
    answer_text: str,
    citations_used: list[SearchResult],
) -> str:
    """Keep high-risk actions only when supported by directive citation sections.

    If a high-risk action sentence is cited solely from non-directive sections,
    replace that sentence with a scoped caveat rather than dropping the whole answer.
    """
    if not answer_text.strip() or not citations_used:
        return answer_text

    kept_units: list[str] = []
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue

        action_type = _high_risk_action_type(unit)
        if action_type is None:
            kept_units.append(unit)
            continue

        cited_indices = _citation_indices_for_unit(unit)
        if not cited_indices:
            kept_units.append(unit)
            continue

        cited_citations = [
            citations_used[index - 1]
            for index in cited_indices
            if 1 <= index <= len(citations_used)
        ]
        if not cited_citations:
            kept_units.append(unit)
            continue
        if all(_citation_has_low_signal(citation) for citation in cited_citations):
            # Avoid over-enforcing when test fixtures or sparse citation payloads
            # lack section metadata/text signal.
            kept_units.append(unit)
            continue

        directive_supported = any(
            _is_directive_citation(citation)
            for citation in cited_citations
        )
        if directive_supported:
            kept_units.append(unit)
            continue

        kept_units.append(
            _high_risk_gap_sentence(
                action_type=action_type,
                citation_group=_format_citation_group(cited_indices),
            )
        )

    return _clean_answer_text(" ".join(kept_units))


def _soften_cross_source_consensus_claims(answer_text: str) -> str:
    if not answer_text.strip():
        return ""
    softened = _CROSS_SOURCE_OVERCLAIM_RE.sub(
        "included in indexed passages",
        answer_text,
    )
    softened = _CROSS_SOURCE_SOFTEN_RE.sub("in indexed passages", softened)
    return _clean_answer_text(softened)


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
        idx: _normalize_text_for_match(_citation_text(citation))
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
        if pattern.search(_citation_text(citation)):
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


def _enforce_requested_scope(
    answer_text: str,
    *,
    query: str | None,
) -> str:
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


def _unit_matches_requested_part(unit: str, query: str) -> bool:
    if _INVESTIGATION_QUERY_HINT_RE.search(query) and _INVESTIGATION_SENTENCE_HINT_RE.search(unit):
        return True
    if _IMAGING_QUERY_HINT_RE.search(query) and _IMAGING_SENTENCE_HINT_RE.search(unit):
        return True
    if _REFERRAL_QUERY_HINT_RE.search(query) and _REFERRAL_SENTENCE_HINT_RE.search(unit):
        return True
    if _TREATMENT_QUERY_HINT_RE.search(query) and _TREATMENT_SENTENCE_HINT_RE.search(unit):
        return True
    return False


def _enforce_urgency_wording_grounding(
    answer_text: str,
    citations_used: list[SearchResult],
) -> str:
    """Balanced mode keeps urgency wording in cited units."""
    if not answer_text.strip() or not citations_used:
        return answer_text
    return answer_text


def _trim_non_query_additional_branches(
    answer_text: str,
    *,
    query: str | None,
) -> str:
    """Drop weakly aligned 'Additionally, if ...' branch sentences.

    These branches are often adjacent recommendation fragments that are not
    directly asked in the current scenario.
    """
    if not answer_text.strip() or not query:
        return answer_text
    query_tokens = _content_tokens(query)
    if not query_tokens:
        return answer_text

    kept_units: list[str] = []
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue

        if not _VALID_CITATION_GROUP_RE.search(unit):
            kept_units.append(unit)
            continue

        if not _ADDITIONAL_BRANCH_PREFIX_RE.search(unit.strip()):
            kept_units.append(unit)
            continue

        overlap = len(_content_tokens(unit).intersection(query_tokens))
        if overlap >= 2 or _unit_matches_requested_part(unit, query):
            kept_units.append(unit)
            continue

    return _clean_answer_text(" ".join(kept_units))


def _enforce_population_alignment(answer_text: str, *, query: str | None) -> str:
    """For adult-only asks, drop child-only cited population statements."""
    if not answer_text.strip() or not query:
        return answer_text

    query_is_adult = bool(_ADULT_QUERY_HINT_RE.search(query))
    query_mentions_child = bool(_CHILD_POPULATION_HINT_RE.search(query))
    if not query_is_adult or query_mentions_child:
        return answer_text

    kept_units: list[str] = []
    for raw_unit in _SENTENCE_SPLIT_RE.split(answer_text):
        unit = (raw_unit or "").strip()
        if not unit:
            continue

        if (
            _VALID_CITATION_GROUP_RE.search(unit)
            and _CHILD_POPULATION_HINT_RE.search(unit)
            and not _ADULT_POPULATION_HINT_RE.search(unit)
        ):
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
    answer = _enforce_grounded_sentences(
        answer,
        has_citations=bool(citations_used),
    )
    answer = _neutralize_unsupported_rationale_clauses(
        answer,
        citations_used,
    )
    answer = _soften_cross_source_consensus_claims(answer)
    answer = _enforce_explicit_timeframe_grounding(
        answer,
        citations_used,
    )
    answer = _enforce_high_risk_action_source_quality(answer, citations_used)
    answer = _enforce_urgency_wording_grounding(
        answer,
        citations_used,
    )
    answer = _trim_non_query_additional_branches(answer, query=query)
    answer = _enforce_population_alignment(answer, query=query)
    answer = _enforce_requested_scope(answer, query=query)
    answer = _enforce_partial_question_coverage(
        answer,
        query=query,
        has_citations=bool(citations_used),
        citations_used=citations_used,
    )
    return answer, citations_used

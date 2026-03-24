from __future__ import annotations

import re
from itertools import pairwise

GENERIC_TOKENS = {
    "about",
    "after",
    "along",
    "best",
    "before",
    "between",
    "could",
    "data",
    "details",
    "evidence",
    "for",
    "from",
    "guideline",
    "guidelines",
    "information",
    "introduction",
    "into",
    "material",
    "overview",
    "recommendation",
    "recommendations",
    "should",
    "statement",
    "summary",
    "supplementary",
    "that",
    "their",
    "there",
    "this",
    "using",
    "when",
    "where",
    "which",
    "while",
    "with",
    "within",
    "would",
}

_POSITIVE_DOC_PATTERNS: tuple[tuple[str, float], ...] = (
    ("guideline", 0.18),
    ("management", 0.14),
    ("diagnosis", 0.12),
    ("initial management", 0.16),
    ("initial assessment", 0.14),
    ("recognition and referral", 0.18),
    ("referral", 0.12),
    ("recommendation", 0.14),
    ("monitoring", 0.16),
    ("investigation", 0.16),
    ("investigations", 0.16),
    ("blood tests", 0.14),
    ("imaging", 0.14),
    ("radiograph", 0.14),
    ("radiographs", 0.14),
    ("triage", 0.16),
    ("advice", 0.12),
    ("prescription", 0.12),
    ("safety", 0.12),
    ("toxicity", 0.12),
    ("source guidance", 0.08),
)

_NEGATIVE_DOC_PATTERNS: tuple[tuple[str, float], ...] = (
    ("terminated appraisal", -0.24),
    ("clinical need and practice", -0.18),
    ("the technologies", -0.14),
    ("context", -0.1),
    ("discussion", -0.14),
    ("audit tool", -0.18),
    ("microsoft word", -0.22),
    ("visual summary", -0.06),
    ("shared learning", -0.08),
    ("manuscript", -0.1),
)

_INTENT_QUERY_MARKERS: tuple[str, ...] = (
    "urgent",
    "urgently",
    "immediate",
    "investigation",
    "investigations",
    "diagnosis",
    "diagnostic",
    "distinguish",
    "differentiate",
    "imaging",
    "radiograph",
    "radiographs",
    "blood tests",
    "baseline",
    "before referral",
    "prior to referral",
    "suspected",
    "refer",
    "referral",
    "monitor",
    "monitoring",
    "toxicity",
    "proteinuria",
    "creatinine",
    "neutropenia",
    "weakness",
    "retention",
    "incontinence",
    "fever",
    "sore throat",
)

_INTENT_POSITIVE_DOC_MARKERS: tuple[str, ...] = (
    "guideline",
    "management",
    "diagnosis",
    "initial management",
    "initial assessment",
    "recognition",
    "referral",
    "monitoring",
    "investigation",
    "investigations",
    "blood tests",
    "imaging",
    "radiograph",
    "triage",
    "advice",
    "recommendation",
    "prescription",
    "safety",
    "toxicity",
)

_INTENT_NEGATIVE_DOC_MARKERS: tuple[str, ...] = (
    "for treating",
    "for preventing",
    "clinical need and practice",
    "the technologies",
    "context",
    "discussion",
    "audit",
)


def informative_tokens(text: str) -> set[str]:
    """Return informative lowercase tokens for lexical relevance checks."""
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(token) >= 3 and token not in GENERIC_TOKENS
    }


def informative_phrases(text: str) -> set[str]:
    """Return adjacent informative token pairs for phrase-level overlap checks."""
    tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(token) >= 3 and token not in GENERIC_TOKENS
    ]
    return {f"{left} {right}" for left, right in pairwise(tokens) if left != right}


def query_overlap_count(question: str, chunk_text: str) -> int:
    """Return the number of informative lexical overlaps between query and chunk."""
    q_tokens = informative_tokens(question)
    c_tokens = informative_tokens(chunk_text)
    return len(q_tokens.intersection(c_tokens)) if q_tokens and c_tokens else 0


def phrase_overlap_count(question: str, chunk_text: str) -> int:
    """Return the number of informative bigram overlaps between query and text."""
    q_phrases = informative_phrases(question)
    c_phrases = informative_phrases(chunk_text)
    return len(q_phrases.intersection(c_phrases)) if q_phrases and c_phrases else 0


def query_overlap_ratio(question: str, candidate_text: str) -> float:
    """Return the fraction of informative query tokens covered by the candidate."""
    q_tokens = informative_tokens(question)
    if not q_tokens:
        return 0.0
    c_tokens = informative_tokens(candidate_text)
    if not c_tokens:
        return 0.0
    return len(q_tokens.intersection(c_tokens)) / len(q_tokens)


def text_quality_score(text: str) -> float:
    """Heuristically score extracted text quality to down-rank garbled OCR chunks."""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return 0.0

    alpha_tokens = [token for token in tokens if any(ch.isalpha() for ch in token)]
    if not alpha_tokens:
        return 0.0

    short_ratio = sum(1 for token in alpha_tokens if len(token) <= 2) / len(
        alpha_tokens
    )
    vowel_ratio = sum(
        1 for token in alpha_tokens if re.search(r"[aeiou]", token.lower())
    ) / len(alpha_tokens)
    whitespace_ratio = min(text.count(" ") / max(len(text), 1), 0.25) / 0.25
    quality = (
        (0.45 * (1.0 - short_ratio)) + (0.4 * vowel_ratio) + (0.15 * whitespace_ratio)
    )
    return max(0.0, min(quality, 1.0))


def document_kind_score(
    *,
    title: str,
    section: str = "",
    doc_type: str = "",
    source_name: str = "",
) -> float:
    """Estimate whether a chunk comes from high-value guidance vs noisier material."""
    haystack = " ".join(
        part for part in (title, section, doc_type, source_name) if part
    ).lower()
    if not haystack:
        return 0.0

    score = 0.0
    for needle, weight in _POSITIVE_DOC_PATTERNS:
        if needle in haystack:
            score += weight
    for needle, weight in _NEGATIVE_DOC_PATTERNS:
        if needle in haystack:
            score += weight

    doc_type_lc = doc_type.lower()
    if "guideline" in doc_type_lc or "guidance" in doc_type_lc:
        score += 0.08
    if "appraisal" in doc_type_lc:
        score -= 0.12

    opaque_title = title.strip()
    if opaque_title and (
        re.fullmatch(r"[A-Za-z]{2,}\d[\w.\- ]*", opaque_title)
        or re.fullmatch(r"[A-Z]{2,}-[A-Z]{2,}\d[\w.\- ]*", opaque_title)
    ):
        score -= 0.08

    return max(-0.3, min(score, 0.3))


def query_intent_alignment_score(
    query: str,
    *,
    title: str,
    section: str = "",
    text: str = "",
    doc_type: str = "",
) -> float:
    """Boost doc types that fit triage/monitoring questions and demote mismatches."""
    query_lc = query.lower()
    if not any(marker in query_lc for marker in _INTENT_QUERY_MARKERS):
        return 0.0

    haystack = " ".join(part for part in (title, section, doc_type, text[:400]) if part)
    haystack_lc = haystack.lower()

    score = 0.0
    if any(marker in haystack_lc for marker in _INTENT_POSITIVE_DOC_MARKERS):
        score += 0.12
    if any(marker in haystack_lc for marker in _INTENT_NEGATIVE_DOC_MARKERS):
        score -= 0.12
    doc_type_lc = doc_type.lower()
    title_lc = title.lower()
    if "appraisal" in doc_type_lc:
        score -= 0.18
    if "for treating" in title_lc or "for preventing" in title_lc:
        score -= 0.12
    if "guideline" in doc_type_lc or "guideline" in title_lc:
        score += 0.06
    return max(-0.18, min(score, 0.18))


def has_query_overlap(question: str, chunk_text: str) -> bool:
    """Return True when the chunk shares informative tokens with the query."""
    return (
        query_overlap_count(question, chunk_text) > 0
        or phrase_overlap_count(question, chunk_text) > 0
    )

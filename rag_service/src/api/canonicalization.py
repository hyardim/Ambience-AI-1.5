from __future__ import annotations

import re

RHEUMATOLOGY = "rheumatology"

RHEUMATOLOGY_CANONICAL_QUERY = (
    "Adult with suspected persistent synovitis of undetermined cause affecting "
    "more than one joint. What investigations are recommended in primary care "
    "before urgent rheumatology referral, including rheumatoid factor (RF), "
    "anti-CCP antibodies, ESR/CRP, and X-ray of hands and feet?"
)

_SWELLING_HINT_RE = re.compile(
    r"\b(swelling|swollen|synovitis|inflammatory arthritis|joint inflammation)\b",
    re.IGNORECASE,
)
_MULTI_JOINT_HINT_RE = re.compile(
    r"\b(more than one joint|multiple joints?|several joints?|polyarticular|"
    r"both wrists|both knees|hands and feet|knees and wrists)\b",
    re.IGNORECASE,
)
_CHRONICITY_HINT_RE = re.compile(
    r"\b(persistent|intermittent|ongoing|chronic)\b|"
    r"\b(?:for|over|since)\s+\d+\s*(?:day|week|month|year)s?\b",
    re.IGNORECASE,
)
_INVESTIGATION_HINT_RE = re.compile(
    r"\b(baseline|blood tests?|investigations?|work[- ]?up|imaging|x-?ray|"
    r"ultrasound|mri|ct|scan)\b",
    re.IGNORECASE,
)
_REFERRAL_HINT_RE = re.compile(
    r"\b(refer|referral|pathway|urgent|urgency|prior to referral|"
    r"before referral)\b",
    re.IGNORECASE,
)

_JOINT_FAMILY_PATTERNS = (
    re.compile(r"\bknee(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bwrist(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bhand(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bfoot|feet\b", re.IGNORECASE),
    re.compile(r"\bankle(?:s)?\b", re.IGNORECASE),
    re.compile(r"\belbow(?:s)?\b", re.IGNORECASE),
    re.compile(r"\bshoulder(?:s)?\b", re.IGNORECASE),
)


def parse_allowed_specialties(raw: str) -> set[str]:
    return {
        part.strip().lower()
        for part in raw.split(",")
        if part and part.strip()
    }


def build_canonical_retrieval_query(
    *,
    query: str,
    specialty: str | None,
    allowed_specialties: set[str],
) -> str | None:
    specialty_norm = (specialty or "").strip().lower()
    if specialty_norm:
        if specialty_norm not in allowed_specialties:
            return None
        if specialty_norm == RHEUMATOLOGY and (
            _is_rheumatology_inflammatory_referral_query(query)
        ):
            return RHEUMATOLOGY_CANONICAL_QUERY
        return None

    if RHEUMATOLOGY in allowed_specialties and (
        _is_rheumatology_inflammatory_referral_query(query)
    ):
        return RHEUMATOLOGY_CANONICAL_QUERY
    return None


def _is_rheumatology_inflammatory_referral_query(query: str) -> bool:
    return (
        _has_multi_joint_swelling(query)
        and bool(_CHRONICITY_HINT_RE.search(query))
        and bool(_INVESTIGATION_HINT_RE.search(query))
        and bool(_REFERRAL_HINT_RE.search(query))
    )


def _has_multi_joint_swelling(query: str) -> bool:
    if not _SWELLING_HINT_RE.search(query):
        return False
    if _MULTI_JOINT_HINT_RE.search(query):
        return True
    joint_family_matches = sum(
        1 for pattern in _JOINT_FAMILY_PATTERNS if pattern.search(query)
    )
    return joint_family_matches >= 2

from __future__ import annotations

import re

RHEUMATOLOGY = "rheumatology"
NEUROLOGY = "neurology"

RHEUMATOLOGY_CANONICAL_QUERY = (
    "Adult with suspected persistent synovitis of undetermined cause affecting "
    "more than one joint. What investigations are recommended in primary care "
    "before urgent rheumatology referral, including rheumatoid factor (RF), "
    "anti-CCP antibodies, ESR/CRP, and X-ray of hands and feet?"
)
NEUROLOGY_NPH_CANONICAL_QUERY = (
    "Adult with difficulty initiating and coordinating walking (gait apraxia), "
    "urinary symptoms, cognitive decline, and ventriculomegaly. Should normal "
    "pressure hydrocephalus be suspected, and should referral to neurology or "
    "an elderly care clinic occur to exclude NPH?"
)
NEUROLOGY_ACUTE_VERTIGO_CANONICAL_QUERY = (
    "Adult with sudden-onset dizziness or vertigo and a focal neurological "
    "deficit (for example diplopia or limb ataxia). Refer immediately for "
    "assessment for a vascular event via local stroke pathways."
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
_GAIT_APRAXIA_HINT_RE = re.compile(
    r"\b(gait apraxia|difficulty initiating (?:and )?coordinating walking|"
    r"difficulty initiating walking|gait initiation difficulty)\b",
    re.IGNORECASE,
)
_URINARY_HINT_RE = re.compile(
    r"\b(urinary (?:incontinence|urgency|frequency)|incontinence|urgency)\b",
    re.IGNORECASE,
)
_COGNITIVE_HINT_RE = re.compile(
    r"\b(cognitive decline|memory (?:decline|problems?)|confusion)\b",
    re.IGNORECASE,
)
_VENTRICULO_NPH_HINT_RE = re.compile(
    r"\b(ventriculomegaly|normal pressure hydrocephalus|hydrocephalus|nph)\b",
    re.IGNORECASE,
)
_SUDDEN_HINT_RE = re.compile(
    r"\b(sudden(?:-onset)?|acute|within\s+\d+\s*(?:minute|hour)s?)\b",
    re.IGNORECASE,
)
_VERTIGO_HINT_RE = re.compile(
    r"\b(vertigo|dizziness|vestibular)\b",
    re.IGNORECASE,
)
_FOCAL_DEFICIT_HINT_RE = re.compile(
    r"\b(diplopia|ataxia|limb ataxia|focal neurological deficit|nystagmus|"
    r"dysarthria|speech disturbance|language difficulty|facial weakness|"
    r"limb weakness|unilateral numbness)\b",
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
    """Parse comma-separated specialties from settings."""
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
    """Return a canonical retrieval query when a specialty rule is triggered."""
    specialty_norm = (specialty or "").strip().lower()
    if specialty_norm:
        if specialty_norm not in allowed_specialties:
            return None
        if specialty_norm == RHEUMATOLOGY and _is_rheumatology_inflammatory_referral_query(  # noqa: E501
            query
        ):
            return RHEUMATOLOGY_CANONICAL_QUERY
        if specialty_norm == NEUROLOGY:
            if _is_neurology_nph_referral_query(query):
                return NEUROLOGY_NPH_CANONICAL_QUERY
            if _is_neurology_acute_vertigo_focal_deficit_query(query):
                return NEUROLOGY_ACUTE_VERTIGO_CANONICAL_QUERY
        return None

    # Specialty may be unset from UI metadata; allow a narrow, high-precision
    # rule trigger for enabled specialties rather than failing closed on null.
    if RHEUMATOLOGY in allowed_specialties and _is_rheumatology_inflammatory_referral_query(  # noqa: E501
        query
    ):
        return RHEUMATOLOGY_CANONICAL_QUERY
    if NEUROLOGY in allowed_specialties:
        if _is_neurology_nph_referral_query(query):
            return NEUROLOGY_NPH_CANONICAL_QUERY
        if _is_neurology_acute_vertigo_focal_deficit_query(query):
            return NEUROLOGY_ACUTE_VERTIGO_CANONICAL_QUERY
    return None


def _is_rheumatology_inflammatory_referral_query(query: str) -> bool:
    """Detect free-text rheumatology referral asks that map to synovitis guidance."""
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


def _is_neurology_nph_referral_query(query: str) -> bool:
    """Detect NPH-style GP asks and map to gait apraxia/NPH referral wording."""
    has_gait_apraxia = bool(_GAIT_APRAXIA_HINT_RE.search(query))
    has_nph_or_ventricles = bool(_VENTRICULO_NPH_HINT_RE.search(query))
    has_supporting_feature = bool(
        _URINARY_HINT_RE.search(query) or _COGNITIVE_HINT_RE.search(query)
    )
    has_referral_intent = bool(_REFERRAL_HINT_RE.search(query))
    return (
        has_gait_apraxia
        and has_nph_or_ventricles
        and has_supporting_feature
        and has_referral_intent
    )


def _is_neurology_acute_vertigo_focal_deficit_query(query: str) -> bool:
    """Detect stroke-pathway vertigo asks and map to guideline language."""
    return (
        bool(_SUDDEN_HINT_RE.search(query))
        and bool(_VERTIGO_HINT_RE.search(query))
        and bool(_FOCAL_DEFICIT_HINT_RE.search(query))
        and bool(_REFERRAL_HINT_RE.search(query))
    )

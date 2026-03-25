from __future__ import annotations

from src.api.canonicalization import (
    NEUROLOGY_ACUTE_VERTIGO_CANONICAL_QUERY,
    NEUROLOGY_NPH_CANONICAL_QUERY,
    RHEUMATOLOGY_CANONICAL_QUERY,
    build_canonical_retrieval_query,
    parse_allowed_specialties,
)


def test_parse_allowed_specialties_handles_csv_whitespace() -> None:
    assert parse_allowed_specialties(" rheumatology, neurology ,cardiology ") == {
        "rheumatology",
        "neurology",
        "cardiology",
    }


def test_rheumatology_canonicalization_triggers_for_joint_swelling_referral_query() -> (
    None
):
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )

    canonical = build_canonical_retrieval_query(
        query=query,
        specialty="rheumatology",
        allowed_specialties={"rheumatology"},
    )

    assert canonical == RHEUMATOLOGY_CANONICAL_QUERY


def test_rheumatology_canonicalization_does_not_trigger_for_acute_gout_query() -> None:
    query = (
        "Acute first MTP swelling for 2 days, likely gout. "
        "What treatment should I start now?"
    )

    canonical = build_canonical_retrieval_query(
        query=query,
        specialty="rheumatology",
        allowed_specialties={"rheumatology"},
    )

    assert canonical is None


def test_rheumatology_canonicalization_triggers_when_specialty_missing() -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )

    canonical = build_canonical_retrieval_query(
        query=query,
        specialty=None,
        allowed_specialties={"rheumatology"},
    )

    assert canonical == RHEUMATOLOGY_CANONICAL_QUERY


def test_neurology_canonicalization_triggers_for_nph_style_query() -> None:
    query = (
        "A 79-year-old has 6 months of gait initiation difficulty, urinary urgency, "
        "and mild cognitive decline. CT head shows ventriculomegaly. Should normal "
        "pressure hydrocephalus be suspected and how urgently should referral occur?"
    )

    canonical = build_canonical_retrieval_query(
        query=query,
        specialty="neurology",
        allowed_specialties={"neurology"},
    )

    assert canonical == NEUROLOGY_NPH_CANONICAL_QUERY


def test_neurology_canonicalization_triggers_for_acute_vertigo_focal_deficit() -> None:
    query = (
        "A 66-year-old has sudden severe vertigo with diplopia and limb ataxia "
        "starting 1 hour ago. What referral urgency is recommended?"
    )

    canonical = build_canonical_retrieval_query(
        query=query,
        specialty="neurology",
        allowed_specialties={"neurology"},
    )

    assert canonical == NEUROLOGY_ACUTE_VERTIGO_CANONICAL_QUERY


def test_neurology_canonicalization_does_not_trigger_for_benign_vertigo_without_focal_deficit() -> (
    None
):
    query = (
        "Adult with recurrent positional vertigo for 3 months without diplopia, "
        "ataxia, weakness, or other focal neurological deficits. Is routine referral "
        "needed?"
    )

    canonical = build_canonical_retrieval_query(
        query=query,
        specialty="neurology",
        allowed_specialties={"neurology"},
    )

    assert canonical is None

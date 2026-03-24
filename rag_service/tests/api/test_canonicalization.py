from __future__ import annotations

from src.api.canonicalization import (
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

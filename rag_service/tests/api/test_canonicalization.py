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


def test_rheumatology_canonicalization_returns_none_for_disallowed_specialty() -> None:
    canonical = build_canonical_retrieval_query(
        query="Joint swelling over months prior to referral with blood tests needed.",
        specialty="neurology",
        allowed_specialties={"rheumatology"},
    )

    assert canonical is None


def test_rheumatology_canonicalization_returns_none_when_allowed_set_missing() -> None:
    canonical = build_canonical_retrieval_query(
        query=(
            "35-year-old with intermittent joint swelling in knees and wrists over "
            "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
            "tests and imaging should be completed prior to referral?"
        ),
        specialty=None,
        allowed_specialties={"neurology"},
    )

    assert canonical is None


def test_rheumatology_canonicalization_detects_multi_joint_by_joint_family() -> None:
    canonical = build_canonical_retrieval_query(
        query=(
            "Intermittent swollen knees and wrists over 4 months. What baseline "
            "investigations are needed before referral?"
        ),
        specialty="rheumatology",
        allowed_specialties={"rheumatology"},
    )

    assert canonical == RHEUMATOLOGY_CANONICAL_QUERY


def test_rheumatology_canonicalization_requires_swelling_signal() -> None:
    canonical = build_canonical_retrieval_query(
        query=(
            "Pain in knees and wrists over 4 months. What baseline "
            "investigations are needed before referral?"
        ),
        specialty="rheumatology",
        allowed_specialties={"rheumatology"},
    )

    assert canonical is None


def test_rheumatology_canonicalization_triggers_when_specialty_missing() -> None:
    canonical = build_canonical_retrieval_query(
        query=(
            "35-year-old with intermittent joint swelling in knees and wrists over "
            "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
            "tests and imaging should be completed prior to referral?"
        ),
        specialty=None,
        allowed_specialties={"rheumatology"},
    )

    assert canonical == RHEUMATOLOGY_CANONICAL_QUERY

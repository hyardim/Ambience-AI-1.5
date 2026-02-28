from __future__ import annotations

from unittest.mock import patch

import pytest

from src.retrieval.filters import FilterConfig, apply_filters
from src.retrieval.fusion import FusedResult

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_result(
    chunk_id: str = "chunk_001",
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_ts_rank: float | None = None,
    specialty: str = "rheumatology",
    source_name: str = "NICE",
    doc_type: str = "guideline",
    content_type: str = "text",
) -> FusedResult:
    return FusedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some clinical text.",
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_ts_rank,
        metadata={
            "specialty": specialty,
            "source_name": source_name,
            "doc_type": doc_type,
            "content_type": content_type,
            "source_url": "https://nice.org.uk",
            "section_title": "Treatment",
            "title": "RA Guidelines",
            "page_start": 1,
            "page_end": 2,
            "section_path": ["Treatment"],
        },
    )


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestApplyFilters:
    def test_returns_filtered_list(self):
        results = [make_result()]
        config = FilterConfig()
        output = apply_filters(results, config)
        assert isinstance(output, list)
        assert all(isinstance(r, FusedResult) for r in output)

    def test_specialty_filter_drops_non_matching(self):
        results = [
            make_result("c1", specialty="rheumatology"),
            make_result("c2", specialty="neurology"),
        ]
        config = FilterConfig(specialty="rheumatology")
        output = apply_filters(results, config)
        assert all(r.metadata["specialty"] == "rheumatology" for r in output)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_source_name_filter_drops_non_matching(self):
        results = [
            make_result("c1", source_name="NICE"),
            make_result("c2", source_name="BSR"),
        ]
        config = FilterConfig(source_name="NICE")
        output = apply_filters(results, config)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_doc_type_filter_drops_non_matching(self):
        results = [
            make_result("c1", doc_type="guideline"),
            make_result("c2", doc_type="protocol"),
        ]
        config = FilterConfig(doc_type="guideline")
        output = apply_filters(results, config)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_content_type_filter_drops_non_matching(self):
        results = [
            make_result("c1", content_type="text"),
            make_result("c2", content_type="table"),
        ]
        config = FilterConfig(content_types=["text"])
        output = apply_filters(results, config)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_content_types_allows_multiple_values(self):
        results = [
            make_result("c1", content_type="text"),
            make_result("c2", content_type="table"),
        ]
        config = FilterConfig(content_types=["text", "table"])
        output = apply_filters(results, config)
        assert len(output) == 2

    def test_multiple_filters_are_anded(self):
        results = [
            make_result("c1", specialty="rheumatology", source_name="NICE"),
            make_result("c2", specialty="rheumatology", source_name="BSR"),
            make_result("c3", specialty="neurology", source_name="NICE"),
        ]
        config = FilterConfig(specialty="rheumatology", source_name="NICE")
        output = apply_filters(results, config)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_none_filters_do_not_filter(self):
        results = [
            make_result("c1", specialty="rheumatology"),
            make_result("c2", specialty="neurology"),
        ]
        config = FilterConfig()  # all None
        output = apply_filters(results, config)
        assert len(output) == 2

    def test_score_threshold_drops_low_scoring_results(self):
        results = [
            make_result("c1", vector_score=0.8),
            make_result("c2", vector_score=0.2),  # below default 0.3
        ]
        config = FilterConfig(score_threshold=0.3)
        output = apply_filters(results, config)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_score_exactly_at_threshold_is_kept(self):
        results = [make_result("c1", vector_score=0.3)]
        config = FilterConfig(score_threshold=0.3)
        output = apply_filters(results, config)
        assert len(output) == 1

    def test_keyword_only_results_not_dropped_by_threshold(self):
        # vector_score=None means chunk came from keyword search only
        results = [make_result("c1", vector_score=None)]
        config = FilterConfig(score_threshold=0.9)  # high threshold
        output = apply_filters(results, config)
        assert len(output) == 1

    def test_all_results_filtered_returns_empty_list(self):
        results = [make_result("c1", vector_score=0.1)]
        config = FilterConfig(score_threshold=0.9)
        output = apply_filters(results, config)
        assert output == []

    def test_all_results_filtered_logs_warning(self):
        results = [make_result("c1", vector_score=0.1)]
        config = FilterConfig(score_threshold=0.9)
        with patch("src.retrieval.filters.logger") as mock_logger:
            apply_filters(results, config)
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("All results removed" in c for c in warning_calls)

    def test_empty_input_returns_empty_list(self):
        assert apply_filters([], FilterConfig()) == []

    def test_rrf_ordering_preserved_after_filtering(self):
        results = [
            make_result("c1", rrf_score=0.05, vector_score=0.9),
            make_result("c2", rrf_score=0.04, vector_score=0.8),
            make_result("c3", rrf_score=0.03, vector_score=0.1),  # dropped
            make_result("c4", rrf_score=0.02, vector_score=0.7),
        ]
        config = FilterConfig(score_threshold=0.3)
        output = apply_filters(results, config)
        assert [r.chunk_id for r in output] == ["c1", "c2", "c4"]

    def test_negative_threshold_raises_value_error(self):
        with pytest.raises(ValueError, match="score_threshold"):
            apply_filters([make_result()], FilterConfig(score_threshold=-0.1))

    def test_threshold_above_one_raises_value_error(self):
        with pytest.raises(ValueError, match="score_threshold"):
            apply_filters([make_result()], FilterConfig(score_threshold=1.1))

    def test_invalid_content_type_raises_value_error(self):
        with pytest.raises(ValueError, match="content_type"):
            apply_filters([make_result()], FilterConfig(content_types=["image"]))

    def test_zero_threshold_keeps_all_results(self):
        results = [
            make_result("c1", vector_score=0.01),
            make_result("c2", vector_score=0.0),
        ]
        config = FilterConfig(score_threshold=0.0)
        output = apply_filters(results, config)
        assert len(output) == 2

    def test_threshold_of_one_drops_all_but_perfect_score(self):
        results = [
            make_result("c1", vector_score=1.0),
            make_result("c2", vector_score=0.99),
        ]
        config = FilterConfig(score_threshold=1.0)
        output = apply_filters(results, config)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

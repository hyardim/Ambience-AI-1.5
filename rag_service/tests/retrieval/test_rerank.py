from __future__ import annotations

from math import exp
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.fusion import FusedResult
from src.retrieval.query import RetrievalError
from src.retrieval.rerank import (
    RankedResult,
    _jaccard_similarity,
    deduplicate,
    rerank,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_fused_result(
    chunk_id: str = "chunk_001",
    text: str = "Some clinical text about methotrexate dosage.",
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_rank: float | None = 0.72,
    metadata: dict[str, Any] | None = None,
) -> FusedResult:
    return FusedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text=text,
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_rank,
        metadata=metadata or {"specialty": "rheumatology"},
    )


def make_ranked_result(
    chunk_id: str = "chunk_001",
    text: str = "Some clinical text about methotrexate dosage.",
    rerank_score: float = 0.85,
    rrf_score: float = 0.03,
    vector_score: float | None = 0.85,
    keyword_rank: float | None = 0.72,
    metadata: dict[str, Any] | None = None,
) -> RankedResult:
    return RankedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text=text,
        rerank_score=rerank_score,
        rrf_score=rrf_score,
        vector_score=vector_score,
        keyword_rank=keyword_rank,
        metadata=metadata or {"specialty": "rheumatology"},
    )


def make_mock_model(logits: list[float]) -> MagicMock:
    mock = MagicMock()
    mock.predict.return_value = logits
    return mock


QUERY = "methotrexate dosage rheumatoid arthritis"


# -----------------------------------------------------------------------
# Fixture: reset module-level model cache between tests
# -----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_model_cache():
    import src.retrieval.rerank as rerank_module

    rerank_module._model = None
    rerank_module._model_name_loaded = None
    yield
    rerank_module._model = None
    rerank_module._model_name_loaded = None


# -----------------------------------------------------------------------
# rerank() tests
# -----------------------------------------------------------------------


class TestRerank:
    def _patch_model(self, logits: list[float]):
        return patch(
            "src.retrieval.rerank._load_model",
            return_value=make_mock_model(logits),
        )

    def test_returns_list_of_ranked_results(self):
        results = [make_fused_result("c1"), make_fused_result("c2")]
        with self._patch_model([2.0, 1.0]):
            output = rerank(QUERY, results)
        assert isinstance(output, list)
        assert all(isinstance(r, RankedResult) for r in output)

    def test_results_ordered_by_rerank_score_descending(self):
        results = [
            make_fused_result("c1"),
            make_fused_result("c2"),
            make_fused_result("c3"),
        ]
        with self._patch_model([1.0, 3.0, 2.0]):
            output = rerank(QUERY, results)
        scores = [r.rerank_score for r in output]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_output(self):
        results = [make_fused_result(f"c{i}") for i in range(10)]
        with self._patch_model([float(i) for i in range(10)]):
            output = rerank(QUERY, results, top_k=3)
        assert len(output) == 3

    def test_rerank_score_is_normalised_between_0_and_1(self):
        results = [make_fused_result("c1")]
        with self._patch_model([5.0]):  # large logit
            output = rerank(QUERY, results)
        assert 0.0 <= output[0].rerank_score <= 1.0

    def test_rerank_score_sigmoid_correctness(self):
        logit = 2.0
        expected = 1.0 / (1.0 + exp(-logit))
        results = [make_fused_result("c1")]
        with self._patch_model([logit]):
            output = rerank(QUERY, results)
        assert abs(output[0].rerank_score - expected) < 1e-6

    def test_rrf_score_preserved_in_output(self):
        results = [make_fused_result("c1", rrf_score=0.042)]
        with self._patch_model([1.0]):
            output = rerank(QUERY, results)
        assert output[0].rrf_score == 0.042

    def test_vector_score_preserved_in_output(self):
        results = [make_fused_result("c1", vector_score=0.91)]
        with self._patch_model([1.0]):
            output = rerank(QUERY, results)
        assert output[0].vector_score == 0.91

    def test_keyword_rank_preserved_in_output(self):
        results = [make_fused_result("c1", keyword_rank=0.55)]
        with self._patch_model([1.0]):
            output = rerank(QUERY, results)
        assert output[0].keyword_rank == 0.55

    def test_empty_input_returns_empty_list(self):
        output = rerank(QUERY, [])
        assert output == []

    def test_model_load_failure_raises_retrieval_error(self):
        with patch(
            "src.retrieval.rerank._load_model",
            side_effect=RetrievalError(
                stage="RERANK",
                query=QUERY,
                message="Failed to load model",
            ),
        ):
            with pytest.raises(RetrievalError) as exc_info:
                rerank(QUERY, [make_fused_result("c1")])
        assert exc_info.value.stage == "RERANK"

    def test_single_pair_scoring_failure_assigns_zero_score(self):
        results = [make_fused_result("c1"), make_fused_result("c2")]
        mock_model = MagicMock()
        # Return one valid logit and one that will fail sigmoid (non-numeric)
        mock_model.predict.return_value = [2.0, float("inf")]

        with patch("src.retrieval.rerank._load_model", return_value=mock_model):
            with patch(
                "src.retrieval.rerank._sigmoid",
                side_effect=[0.88, Exception("sigmoid failed")],
            ):
                output = rerank(QUERY, results)

        scores = {r.chunk_id: r.rerank_score for r in output}
        assert scores["c2"] == 0.0
        assert scores["c1"] == 0.88

    def test_large_input_logs_warning(self):
        results = [make_fused_result(f"c{i}") for i in range(51)]
        logits = [1.0] * 51
        with patch(
            "src.retrieval.rerank._load_model", return_value=make_mock_model(logits)
        ):
            with patch("src.retrieval.rerank.logger") as mock_logger:
                rerank(QUERY, results)
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("51" in c for c in warning_calls)

    def test_all_pairs_scored_in_single_batch(self):
        results = [make_fused_result(f"c{i}") for i in range(5)]
        mock_model = make_mock_model([1.0] * 5)
        with patch("src.retrieval.rerank._load_model", return_value=mock_model):
            rerank(QUERY, results)
        assert mock_model.predict.call_count == 1
        call_args = mock_model.predict.call_args[0][0]
        assert len(call_args) == 5

    def test_model_loaded_once_across_multiple_calls(self):
        results = [make_fused_result("c1")]
        with patch(
            "src.retrieval.rerank._load_model", return_value=make_mock_model([1.0])
        ) as mock_load:
            rerank(QUERY, results)
            rerank(QUERY, results)
        # _load_model called twice but CrossEncoder constructor should be called once
        # — cache tested via the module-level fixture + direct cache test below
        assert mock_load.call_count == 2  # _load_model itself handles caching

    def test_model_cache_prevents_reload(self):
        import src.retrieval.rerank as rerank_module

        with patch("src.retrieval.rerank.CrossEncoder", create=True) as mock_cls:
            mock_cls.return_value = make_mock_model([1.0])
            with patch(
                "src.retrieval.rerank._load_model", wraps=rerank_module._load_model
            ):
                # Manually populate cache
                rerank_module._model = make_mock_model([1.0, 1.0])
                rerank_module._model_name_loaded = (
                    "cross-encoder/ms-marco-MiniLM-L-6-v2"
                )
                results = [make_fused_result("c1"), make_fused_result("c2")]
                rerank(QUERY, results)
            mock_cls.assert_not_called()


# -----------------------------------------------------------------------
# deduplicate() tests
# -----------------------------------------------------------------------


class TestDeduplicate:
    def test_deduplicate_drops_near_duplicates(self):
        text_a = "methotrexate is used for rheumatoid arthritis treatment"
        text_b = "methotrexate is used for rheumatoid arthritis treatment and more"
        results = [
            make_ranked_result("c1", text=text_a, rerank_score=0.9),
            make_ranked_result("c2", text=text_b, rerank_score=0.7),
        ]
        output = deduplicate(results, similarity_threshold=0.7)
        assert len(output) == 1
        assert output[0].chunk_id == "c1"

    def test_deduplicate_keeps_higher_scoring_result(self):
        text_a = "methotrexate dosage for rheumatoid arthritis patients"
        text_b = "methotrexate dosage for rheumatoid arthritis patients weekly"
        results = [
            make_ranked_result("c1", text=text_a, rerank_score=0.6),
            make_ranked_result("c2", text=text_b, rerank_score=0.9),
        ]
        output = deduplicate(results, similarity_threshold=0.7)
        assert len(output) == 1
        assert output[0].chunk_id == "c2"

    def test_deduplicate_preserves_unique_results(self):
        results = [
            make_ranked_result("c1", text="methotrexate dosage rheumatoid arthritis"),
            make_ranked_result(
                "c2", text="hydroxychloroquine lupus treatment protocol"
            ),
            make_ranked_result(
                "c3", text="biologics TNF inhibitors psoriatic arthritis"
            ),
        ]
        output = deduplicate(results, similarity_threshold=0.85)
        assert len(output) == 3

    def test_deduplicate_empty_input_returns_empty(self):
        assert deduplicate([]) == []

    def test_invalid_similarity_threshold_raises_value_error(self):
        results = [make_ranked_result("c1")]
        with pytest.raises(ValueError, match="similarity_threshold"):
            deduplicate(results, similarity_threshold=1.5)

    def test_invalid_negative_threshold_raises_value_error(self):
        results = [make_ranked_result("c1")]
        with pytest.raises(ValueError, match="similarity_threshold"):
            deduplicate(results, similarity_threshold=-0.1)

    def test_similarity_threshold_controls_aggressiveness(self):
        text_a = "methotrexate treatment rheumatoid arthritis"
        text_b = "methotrexate treatment rheumatoid arthritis weekly dose"
        results = [
            make_ranked_result("c1", text=text_a, rerank_score=0.9),
            make_ranked_result("c2", text=text_b, rerank_score=0.7),
        ]
        # high threshold — similar but not duplicate, both kept
        output_strict = deduplicate(results, similarity_threshold=0.99)
        assert len(output_strict) == 2

        # low threshold — treated as duplicates, one dropped
        output_loose = deduplicate(results, similarity_threshold=0.5)
        assert len(output_loose) == 1


# -----------------------------------------------------------------------
# _jaccard_similarity() tests
# -----------------------------------------------------------------------


class TestJaccardSimilarity:
    def test_identical_strings_return_one(self):
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_completely_different_strings_return_zero(self):
        assert _jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial_overlap_computed_correctly(self):
        # tokens_a = {a, b, c}, tokens_b = {b, c, d}
        # intersection = {b, c}, union = {a, b, c, d}
        # jaccard = 2/4 = 0.5
        result = _jaccard_similarity("a b c", "b c d")
        assert abs(result - 0.5) < 1e-9

    def test_both_empty_strings_return_one(self):
        assert _jaccard_similarity("", "") == 1.0

    def test_case_insensitive(self):
        assert _jaccard_similarity("Hello World", "hello world") == 1.0

    def test_one_empty_string_returns_zero(self):
        assert _jaccard_similarity("hello world", "") == 0.0

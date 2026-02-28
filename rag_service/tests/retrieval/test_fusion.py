from __future__ import annotations

from typing import Any

from src.retrieval.fusion import FusedResult, reciprocal_rank_fusion
from src.retrieval.keyword_search import KeywordSearchResult
from src.retrieval.vector_search import VectorSearchResult

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_vector_result(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    score: float = 0.85,
    metadata: dict[str, Any] | None = None,
) -> VectorSearchResult:
    return VectorSearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=text,
        score=score,
        metadata=metadata or {"specialty": "rheumatology"},
    )


def make_keyword_result(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    rank: float = 0.72,
    metadata: dict[str, Any] | None = None,
) -> KeywordSearchResult:
    return KeywordSearchResult(
        chunk_id=chunk_id,
        doc_id=doc_id,
        text=text,
        rank=rank,
        metadata=metadata or {"specialty": "rheumatology"},
    )


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestReciprocalRankFusion:
    def test_returns_list_of_fused_results(self):
        vector = [make_vector_result("c1")]
        keyword = [make_keyword_result("c2")]
        results = reciprocal_rank_fusion(vector, keyword)
        assert isinstance(results, list)
        assert all(isinstance(r, FusedResult) for r in results)

    def test_result_is_pydantic_model(self):
        results = reciprocal_rank_fusion([make_vector_result("c1")], [])
        assert hasattr(results[0], "model_dump")

    def test_rrf_score_computed_correctly_single_list(self):
        # chunk at rank 1 in vector only: 1/(60+1)
        vector = [make_vector_result("c1")]
        results = reciprocal_rank_fusion(vector, [], k=60)
        expected = 1.0 / (60 + 1)
        assert abs(results[0].rrf_score - expected) < 1e-9

    def test_rrf_score_computed_correctly_both_lists(self):
        # chunk_A: vector_rank=1, keyword_rank=3
        # rrf = 1/(60+1) + 1/(60+3)
        vector = [
            make_vector_result("chunk_A"),
            make_vector_result("chunk_B"),
        ]
        keyword = [
            make_keyword_result("chunk_C"),
            make_keyword_result("chunk_D"),
            make_keyword_result("chunk_A"),
        ]
        results = reciprocal_rank_fusion(vector, keyword, k=60)
        result = next(r for r in results if r.chunk_id == "chunk_A")
        expected = 1.0 / (60 + 1) + 1.0 / (60 + 3)
        assert abs(result.rrf_score - expected) < 1e-9

    def test_chunk_in_both_lists_scores_higher_than_either_alone(self):
        vector = [
            make_vector_result("shared"),
            make_vector_result("vector_only"),
        ]
        keyword = [
            make_keyword_result("shared"),
            make_keyword_result("keyword_only"),
        ]
        results = reciprocal_rank_fusion(vector, keyword)
        scores = {r.chunk_id: r.rrf_score for r in results}
        assert scores["shared"] > scores["vector_only"]
        assert scores["shared"] > scores["keyword_only"]

    def test_results_ordered_by_rrf_score_descending(self):
        vector = [make_vector_result(f"c{i}") for i in range(5)]
        keyword = [make_keyword_result("c0")]  # c0 in both — ranks highest
        results = reciprocal_rank_fusion(vector, keyword)
        scores = [r.rrf_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_output(self):
        vector = [make_vector_result(f"c{i}") for i in range(15)]
        keyword = [make_keyword_result(f"c{i}") for i in range(15)]
        results = reciprocal_rank_fusion(vector, keyword, top_k=5)
        assert len(results) == 5

    def test_top_k_returns_highest_scoring_results(self):
        # c0 appears in both lists so should rank highest
        vector = [make_vector_result("c0"), make_vector_result("c1")]
        keyword = [make_keyword_result("c0"), make_keyword_result("c2")]
        results = reciprocal_rank_fusion(vector, keyword, top_k=1)
        assert len(results) == 1
        assert results[0].chunk_id == "c0"

    def test_empty_vector_results_fuses_keyword_only(self):
        keyword = [make_keyword_result("c1"), make_keyword_result("c2")]
        results = reciprocal_rank_fusion([], keyword)
        assert len(results) == 2
        assert all(r.vector_score is None for r in results)

    def test_empty_keyword_results_fuses_vector_only(self):
        vector = [make_vector_result("c1"), make_vector_result("c2")]
        results = reciprocal_rank_fusion(vector, [])
        assert len(results) == 2
        assert all(r.keyword_rank is None for r in results)

    def test_both_empty_returns_empty_list(self):
        assert reciprocal_rank_fusion([], []) == []

    def test_vector_score_preserved_in_output(self):
        vector = [make_vector_result("c1", score=0.91)]
        results = reciprocal_rank_fusion(vector, [])
        assert results[0].vector_score == 0.91

    def test_keyword_rank_preserved_in_output(self):
        keyword = [make_keyword_result("c1", rank=0.55)]
        results = reciprocal_rank_fusion([], keyword)
        assert results[0].keyword_rank == 0.55

    def test_vector_score_none_when_chunk_only_in_keyword_results(self):
        keyword = [make_keyword_result("c1")]
        results = reciprocal_rank_fusion([], keyword)
        assert results[0].vector_score is None

    def test_keyword_rank_none_when_chunk_only_in_vector_results(self):
        vector = [make_vector_result("c1")]
        results = reciprocal_rank_fusion(vector, [])
        assert results[0].keyword_rank is None

    def test_duplicate_chunk_id_in_vector_input_deduplicated(self):
        vector = [
            make_vector_result("c1", score=0.9),
            make_vector_result("c1", score=0.5),  # duplicate
        ]
        results = reciprocal_rank_fusion(vector, [])
        assert [r.chunk_id for r in results].count("c1") == 1

    def test_duplicate_chunk_id_in_keyword_input_deduplicated(self):
        keyword = [
            make_keyword_result("c1", rank=0.9),
            make_keyword_result("c1", rank=0.5),  # duplicate
        ]
        results = reciprocal_rank_fusion([], keyword)
        assert [r.chunk_id for r in results].count("c1") == 1

    def test_duplicate_keeps_highest_ranked_occurrence(self):
        # first occurrence is rank 1 → rrf = 1/(60+1)
        # second occurrence is rank 2 → should be discarded
        vector = [
            make_vector_result("c1"),  # rank 1 — keep
            make_vector_result("c1"),  # rank 2 — discard
        ]
        results = reciprocal_rank_fusion(vector, [])
        expected = 1.0 / (60 + 1)
        assert abs(results[0].rrf_score - expected) < 1e-9

    def test_custom_k_value_changes_scores(self):
        vector = [make_vector_result("c1")]
        results_k60 = reciprocal_rank_fusion(vector, [], k=60)
        results_k1 = reciprocal_rank_fusion(vector, [], k=1)
        assert results_k60[0].rrf_score != results_k1[0].rrf_score

    def test_metadata_preserved_from_vector_result(self):
        meta = {"specialty": "neurology", "source_name": "NICE"}
        vector = [make_vector_result("c1", metadata=meta)]
        results = reciprocal_rank_fusion(vector, [])
        assert results[0].metadata == meta

    def test_metadata_preserved_from_keyword_result(self):
        meta = {"specialty": "rheumatology", "source_name": "BSR"}
        keyword = [make_keyword_result("c1", metadata=meta)]
        results = reciprocal_rank_fusion([], keyword)
        assert results[0].metadata == meta

    def test_vector_metadata_takes_precedence_for_shared_chunk(self):
        # vector is processed first — its metadata wins for shared chunks
        vector_meta = {"specialty": "neurology"}
        keyword_meta = {"specialty": "rheumatology"}
        vector = [make_vector_result("c1", metadata=vector_meta)]
        keyword = [make_keyword_result("c1", metadata=keyword_meta)]
        results = reciprocal_rank_fusion(vector, keyword)
        assert results[0].metadata == vector_meta

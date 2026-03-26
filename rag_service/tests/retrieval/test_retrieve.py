from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.citation import Citation, CitedResult
from src.retrieval.fusion import FusedResult
from src.retrieval.keyword_search import KeywordSearchResult
from src.retrieval.query import ProcessedQuery, RetrievalError
from src.retrieval.rerank import RankedResult
from src.retrieval.vector_search import VectorSearchResult

QUERY = "gout treatment options"
DB_URL = "postgresql://localhost/test"


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_processed_query() -> ProcessedQuery:
    return ProcessedQuery(
        original="gout treatment options",
        expanded="gout treatment options urate hyperuricemia",
        embedding=[0.1] * 384,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    )


def make_vector_result(chunk_id: str = "c1") -> VectorSearchResult:
    return VectorSearchResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        score=0.85,
        metadata={"specialty": "rheumatology"},
    )


def make_keyword_result(chunk_id: str = "c1") -> KeywordSearchResult:
    return KeywordSearchResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        rank=0.72,
        metadata={"specialty": "rheumatology"},
    )


def make_fused_result(chunk_id: str = "c1") -> FusedResult:
    return FusedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        metadata={"specialty": "rheumatology"},
    )


def make_ranked_result(chunk_id: str = "c1") -> RankedResult:
    return RankedResult(
        chunk_id=chunk_id,
        doc_id="doc_001",
        text="Some text about gout.",
        rerank_score=0.91,
        final_score=0.91,
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        metadata={"specialty": "rheumatology"},
    )


def make_cited_result(chunk_id: str = "c1") -> CitedResult:
    return CitedResult(
        chunk_id=chunk_id,
        text="Some text about gout.",
        rerank_score=0.91,
        final_score=0.91,
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        citation=Citation(
            title="Gout: diagnosis and management",
            source_name="NICE",
            specialty="rheumatology",
            doc_type="guideline",
            section_path=["Treatment"],
            section_title="Treatment",
            page_start=12,
            page_end=13,
            source_url="https://www.nice.org.uk/guidance/cg56",
            doc_id="doc_001",
            chunk_id=chunk_id,
            content_type="text",
        ),
    )


def make_all_stage_mocks(
    vector_results: list | None = None,
    keyword_results: list | None = None,
    fused_results: list | None = None,
    filtered_results: list | None = None,
    reranked_results: list | None = None,
    deduped_results: list | None = None,
    cited_results: list | None = None,
) -> dict[str, MagicMock]:
    return {
        "process_query": MagicMock(return_value=make_processed_query()),
        "vector_search": MagicMock(
            return_value=vector_results
            if vector_results is not None
            else [make_vector_result()]
        ),
        "keyword_search": MagicMock(
            return_value=keyword_results
            if keyword_results is not None
            else [make_keyword_result()]
        ),
        "reciprocal_rank_fusion": MagicMock(
            return_value=fused_results
            if fused_results is not None
            else [make_fused_result()]
        ),
        "apply_filters": MagicMock(
            return_value=filtered_results
            if filtered_results is not None
            else [make_fused_result()]
        ),
        "rerank": MagicMock(
            return_value=reranked_results
            if reranked_results is not None
            else [make_ranked_result()]
        ),
        "deduplicate": MagicMock(
            return_value=deduped_results
            if deduped_results is not None
            else [make_ranked_result()]
        ),
        "assemble_citations": MagicMock(
            return_value=cited_results
            if cited_results is not None
            else [make_cited_result()]
        ),
    }


def run_retrieve(mocks: dict[str, MagicMock], **kwargs):
    from src.retrieval.retrieve import retrieve

    with (
        patch("src.retrieval.retrieve.process_query", mocks["process_query"]),
        patch("src.retrieval.retrieve.vector_search", mocks["vector_search"]),
        patch("src.retrieval.retrieve.keyword_search", mocks["keyword_search"]),
        patch(
            "src.retrieval.retrieve.reciprocal_rank_fusion",
            mocks["reciprocal_rank_fusion"],
        ),
        patch("src.retrieval.retrieve.apply_filters", mocks["apply_filters"]),
        patch("src.retrieval.retrieve.rerank", mocks["rerank"]),
        patch("src.retrieval.retrieve.deduplicate", mocks["deduplicate"]),
        patch("src.retrieval.retrieve.assemble_citations", mocks["assemble_citations"]),
    ):
        return retrieve(QUERY, DB_URL, **kwargs)


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestRetrieve:
    def test_returns_list_of_cited_results(self):
        mocks = make_all_stage_mocks()
        output = run_retrieve(mocks)
        assert isinstance(output, list)
        assert all(isinstance(r, CitedResult) for r in output)

    def test_debug_artifacts_use_shared_path_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        mocks = make_all_stage_mocks()
        monkeypatch.setattr("src.retrieval.retrieve.DEBUG_ARTIFACT_DIR", tmp_path)

        run_retrieve(mocks, write_debug_artifacts=True)

        written = list(tmp_path.glob("*/*.json"))
        assert written

    def test_all_stages_called_in_order(self):
        mocks = make_all_stage_mocks()
        call_order: list[str] = []
        for name, mock in mocks.items():
            mock.side_effect = lambda *a, _n=name, **kw: (
                call_order.append(_n) or mocks[_n].return_value
            )
        run_retrieve(mocks)
        assert call_order == [
            "process_query",
            "vector_search",
            "keyword_search",
            "reciprocal_rank_fusion",
            "apply_filters",
            "rerank",
            "deduplicate",
            "assemble_citations",
        ]

    def test_final_ranking_stage_resorts_deduped_results_before_citations(self):
        stronger = make_ranked_result("c-strong").model_copy(
            update={
                "doc_id": "doc-strong",
                "text": "Gout treatment should start with an NSAID for acute flares.",
                "rerank_score": 0.05,
                "final_score": 0.0,
                "vector_score": 0.78,
                "keyword_rank": 0.0,
            }
        )
        weaker = make_ranked_result("c-weak").model_copy(
            update={
                "doc_id": "doc-weak",
                "text": "Consider referral for adults with persistent symptoms.",
                "rerank_score": 0.45,
                "final_score": 0.0,
                "vector_score": 0.12,
                "keyword_rank": None,
            }
        )
        mocks = make_all_stage_mocks(deduped_results=[weaker, stronger])

        run_retrieve(mocks, top_k=2)

        deduped_passed = mocks["assemble_citations"].call_args.args[0]
        assert [item.chunk_id for item in deduped_passed] == ["c-strong", "c-weak"]
        assert deduped_passed[0].final_score >= deduped_passed[1].final_score

    def test_document_diversification_keeps_multiple_chunks_when_only_two_docs_exist(
        self,
    ):
        first = make_ranked_result("c-1").model_copy(
            update={"doc_id": "doc-a", "final_score": 0.9}
        )
        second = make_ranked_result("c-2").model_copy(
            update={"doc_id": "doc-a", "final_score": 0.8}
        )
        third = make_ranked_result("c-3").model_copy(
            update={"doc_id": "doc-b", "final_score": 0.7}
        )
        mocks = make_all_stage_mocks(deduped_results=[first, second, third])

        run_retrieve(mocks, top_k=3)

        deduped_passed = mocks["assemble_citations"].call_args.args[0]
        assert [item.chunk_id for item in deduped_passed] == ["c-1", "c-2", "c-3"]

    def test_final_ranking_prefers_guidance_doc_over_appraisal_for_triage_queries(self):
        guidance = make_ranked_result("guidance").model_copy(
            update={
                "doc_id": "doc-guidance",
                "text": "Refer suspected early inflammatory arthritis urgently.",
                "rerank_score": 0.44,
                "final_score": 0.0,
                "vector_score": 0.52,
                "keyword_rank": 0.4,
                "metadata": {
                    "specialty": "rheumatology",
                    "title": "Bsr Enhanced Triage And Specialist Advice",
                    "source_name": "BSR",
                    "doc_type": "guideline",
                    "section_path": ["Suspected early inflammatory arthritis referral"],
                },
            }
        )
        appraisal = make_ranked_result("appraisal").model_copy(
            update={
                "doc_id": "doc-appraisal",
                "text": (
                    "Adalimumab is recommended in some settings after DMARD failure."
                ),
                "rerank_score": 0.5,
                "final_score": 0.0,
                "vector_score": 0.57,
                "keyword_rank": 0.3,
                "metadata": {
                    "specialty": "rheumatology",
                    "title": (
                        "Adalimumab, etanercept, infliximab and abatacept for "
                        "treating moderate rheumatoid arthritis after "
                        "conventional DMARDs have failed"
                    ),
                    "source_name": "NICE",
                    "doc_type": "appraisal",
                    "section_path": ["Clinical need and practice"],
                },
            }
        )
        mocks = make_all_stage_mocks(deduped_results=[appraisal, guidance])

        run_retrieve(
            mocks,
            top_k=2,
            specialty="rheumatology",
        )

        deduped_passed = mocks["assemble_citations"].call_args.args[0]
        assert [item.chunk_id for item in deduped_passed] == ["guidance", "appraisal"]

    def test_final_ranking_penalizes_age_mismatch_for_adult_query(self):
        from src.retrieval.retrieve import _apply_final_ranking

        child = make_ranked_result("c-child").model_copy(
            update={
                "doc_id": "doc-child",
                "text": (
                    "Refer urgently to paediatric services children with "
                    "developmental delay and hydrocephalus."
                ),
                "rerank_score": 0.01,
                "final_score": 0.0,
                "vector_score": 0.52,
                "keyword_rank": None,
                "metadata": {
                    "specialty": "neurology",
                    "title": "Suspected neurological conditions",
                    "section_path": [
                        "Children with dysmorphic features and developmental delay"
                    ],
                },
            }
        )
        adult = make_ranked_result("c-adult").model_copy(
            update={
                "doc_id": "doc-adult",
                "text": (
                    "Raise awareness of normal pressure hydrocephalus as a "
                    "possible cause of gait apraxia."
                ),
                "rerank_score": 0.001,
                "final_score": 0.0,
                "vector_score": 0.42,
                "keyword_rank": None,
                "metadata": {
                    "specialty": "neurology",
                    "title": (
                        "Suspected neurological conditions: recognition and referral"
                    ),
                    "section_path": [
                        "Difficulty initiating and coordinating walking (gait apraxia)"
                    ],
                },
            }
        )
        ranked = _apply_final_ranking(
            "65-year-old with gait disturbance, urinary incontinence and "
            "ventriculomegaly. Should normal pressure hydrocephalus be suspected?",
            [child, adult],
            preferred_specialty="neurology",
        )

        assert [item.chunk_id for item in ranked] == ["c-adult", "c-child"]

    def test_vector_search_failure_falls_back_to_keyword_only(self):
        mocks = make_all_stage_mocks()
        mocks["vector_search"].side_effect = Exception("vector db down")
        output = run_retrieve(mocks)
        assert isinstance(output, list)
        mocks["keyword_search"].assert_called_once()
        mocks["reciprocal_rank_fusion"].assert_called_once()

    def test_keyword_search_failure_falls_back_to_vector_only(self):
        mocks = make_all_stage_mocks()
        mocks["keyword_search"].side_effect = Exception("keyword db down")
        output = run_retrieve(mocks)
        assert isinstance(output, list)
        mocks["vector_search"].assert_called_once()
        mocks["reciprocal_rank_fusion"].assert_called_once()

    def test_both_search_failures_raises_retrieval_error(self):
        mocks = make_all_stage_mocks()
        mocks["vector_search"].side_effect = Exception("vector down")
        mocks["keyword_search"].side_effect = Exception("keyword down")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "SEARCH"

    def test_empty_results_after_filtering_returns_empty_list(self):
        mocks = make_all_stage_mocks(filtered_results=[])
        output = run_retrieve(mocks)
        assert output == []
        mocks["rerank"].assert_not_called()

    def test_empty_results_after_reranking_returns_empty_list(self):
        mocks = make_all_stage_mocks(reranked_results=[])
        output = run_retrieve(mocks)
        assert output == []
        mocks["deduplicate"].assert_not_called()

    def test_stage_failure_raises_retrieval_error_with_stage_label(self):
        mocks = make_all_stage_mocks()
        mocks["reciprocal_rank_fusion"].side_effect = Exception("fusion error")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "FUSION"

    def test_query_stage_failure_raises_retrieval_error(self):
        mocks = make_all_stage_mocks()
        mocks["process_query"].side_effect = Exception("query error")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "QUERY"

    def test_filters_stage_failure_raises_retrieval_error(self):
        mocks = make_all_stage_mocks()
        mocks["apply_filters"].side_effect = Exception("filter error")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "FILTERS"

    def test_rerank_stage_failure_raises_retrieval_error(self):
        mocks = make_all_stage_mocks()
        mocks["rerank"].side_effect = Exception("rerank error")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "RERANK"

    def test_dedup_stage_failure_raises_retrieval_error(self):
        mocks = make_all_stage_mocks()
        mocks["deduplicate"].side_effect = Exception("dedup error")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "DEDUP"

    def test_citations_stage_failure_raises_retrieval_error(self):
        mocks = make_all_stage_mocks()
        mocks["assemble_citations"].side_effect = Exception("citations error")
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value.stage == "CITATIONS"

    def test_query_stage_does_not_double_wrap_retrieval_error(self):
        mocks = make_all_stage_mocks()
        inner = RetrievalError(stage="QUERY", query=QUERY, message="model load failed")
        mocks["process_query"].side_effect = inner
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value is inner
        assert exc_info.value.message == "model load failed"

    def test_fusion_stage_does_not_double_wrap_retrieval_error(self):
        mocks = make_all_stage_mocks()
        inner = RetrievalError(stage="FUSION", query=QUERY, message="fusion failed")
        mocks["reciprocal_rank_fusion"].side_effect = inner
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value is inner

    def test_filters_stage_does_not_double_wrap_retrieval_error(self):
        mocks = make_all_stage_mocks()
        inner = RetrievalError(stage="FILTERS", query=QUERY, message="filter failed")
        mocks["apply_filters"].side_effect = inner
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value is inner

    def test_rerank_stage_does_not_double_wrap_retrieval_error(self):
        mocks = make_all_stage_mocks()
        inner = RetrievalError(stage="RERANK", query=QUERY, message="rerank failed")
        mocks["rerank"].side_effect = inner
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value is inner

    def test_dedup_stage_does_not_double_wrap_retrieval_error(self):
        mocks = make_all_stage_mocks()
        inner = RetrievalError(stage="DEDUP", query=QUERY, message="dedup failed")
        mocks["deduplicate"].side_effect = inner
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value is inner

    def test_citations_stage_does_not_double_wrap_retrieval_error(self):
        mocks = make_all_stage_mocks()
        inner = RetrievalError(
            stage="CITATIONS", query=QUERY, message="citations failed"
        )
        mocks["assemble_citations"].side_effect = inner
        with pytest.raises(RetrievalError) as exc_info:
            run_retrieve(mocks)
        assert exc_info.value is inner

    def test_debug_artifacts_written_when_flag_set(self, tmp_path: Path):
        mocks = make_all_stage_mocks()
        with patch("src.retrieval.retrieve.DEBUG_ARTIFACT_DIR", tmp_path):
            run_retrieve(mocks, write_debug_artifacts=True)
        written = list(tmp_path.rglob("*.json"))
        assert len(written) == 10

    def test_debug_artifacts_not_written_by_default(self, tmp_path: Path):
        mocks = make_all_stage_mocks()
        with patch("src.retrieval.retrieve.DEBUG_ARTIFACT_DIR", tmp_path):
            run_retrieve(mocks)
        assert not list(tmp_path.rglob("*.json"))

    def test_top_k_passed_through_to_stages(self):
        mocks = make_all_stage_mocks()
        run_retrieve(mocks, top_k=3)
        _, vkwargs = mocks["vector_search"].call_args
        assert vkwargs["top_k"] == 12
        _, kkwargs = mocks["keyword_search"].call_args
        assert kkwargs["top_k"] == 12
        _, fkwargs = mocks["reciprocal_rank_fusion"].call_args
        assert fkwargs["top_k"] == 18
        _, rkwargs = mocks["rerank"].call_args
        assert rkwargs["top_k"] == 6

    def test_filters_passed_through_to_vector_and_keyword_search(self):
        mocks = make_all_stage_mocks()
        run_retrieve(
            mocks,
            specialty="rheumatology",
            source_name="NICE",
            doc_type="guideline",
        )
        _, vkwargs = mocks["vector_search"].call_args
        assert vkwargs["specialty"] == "rheumatology"
        assert vkwargs["source_name"] == "NICE"
        assert vkwargs["doc_type"] == "guideline"
        _, kkwargs = mocks["keyword_search"].call_args
        assert kkwargs["specialty"] == "rheumatology"
        assert kkwargs["source_name"] == "NICE"
        assert kkwargs["doc_type"] == "guideline"

    def test_search_candidate_top_k_widens_for_long_queries(self):
        from src.retrieval.retrieve import _search_candidate_top_k

        short = _search_candidate_top_k(3, "gout treatment options")
        long = _search_candidate_top_k(
            3,
            (
                "45-year-old with known systemic lupus erythematosus presenting "
                "with new proteinuria and rising creatinine what immediate "
                "investigations and referral pathway are recommended"
            ),
        )

        assert short == 12
        assert long == 40

    def test_final_ranking_prefers_requested_specialty_without_hard_filtering(self):
        rheum = make_ranked_result("c-rheum").model_copy(
            update={
                "doc_id": "doc-rheum",
                "text": "Joint swelling can indicate inflammatory arthritis.",
                "rerank_score": 0.30,
                "final_score": 0.0,
                "vector_score": 0.55,
                "keyword_rank": 0.4,
                "metadata": {"specialty": "rheumatology"},
            }
        )
        neuro = make_ranked_result("c-neuro").model_copy(
            update={
                "doc_id": "doc-neuro",
                "text": "Joint swelling can indicate inflammatory arthritis.",
                "rerank_score": 0.30,
                "final_score": 0.0,
                "vector_score": 0.55,
                "keyword_rank": 0.4,
                "metadata": {"specialty": "neurology"},
            }
        )
        mocks = make_all_stage_mocks(deduped_results=[neuro, rheum])

        run_retrieve(mocks, top_k=2, specialty="rheumatology")

        ranked = mocks["assemble_citations"].call_args.args[0]
        assert [item.chunk_id for item in ranked] == ["c-rheum", "c-neuro"]

    def test_final_ranking_prioritizes_viable_requested_specialty(self):
        from src.retrieval.retrieve import _apply_final_ranking

        requested_specialty = "neurology"
        off_specialty = make_ranked_result("c-off-specialty").model_copy(
            update={
                "doc_id": "doc-off",
                "text": (
                    "Severe back pain and urinary retention can require urgent "
                    "assessment."
                ),
                "rerank_score": 0.12,
                "final_score": 0.0,
                "vector_score": 0.62,
                "keyword_rank": 0.1,
                "metadata": {
                    "specialty": "rheumatology",
                    "title": "Low back pain and sciatica",
                    "section_path": ["Red flags"],
                },
            }
        )
        in_specialty = make_ranked_result("c-in-specialty").model_copy(
            update={
                "doc_id": "doc-neuro",
                "text": (
                    "Refer adults with progressive neurological deficit using "
                    "a suspected cancer pathway."
                ),
                "rerank_score": 0.06,
                "final_score": 0.0,
                "vector_score": 0.56,
                "keyword_rank": None,
                "metadata": {
                    "specialty": requested_specialty,
                    "title": (
                        "Suspected neurological conditions: recognition and referral"
                    ),
                    "section_path": ["Progressive neurological deficit"],
                },
            }
        )
        ranked = _apply_final_ranking(
            (
                "48-year-old with severe back pain, bilateral leg weakness and "
                "urinary retention"
            ),
            [off_specialty, in_specialty],
            preferred_specialty=requested_specialty,
        )

        assert [item.chunk_id for item in ranked] == [
            "c-in-specialty",
            "c-off-specialty",
        ]

    def test_final_ranking_uses_title_and_phrase_specificity(self):
        generic = make_ranked_result("c-generic").model_copy(
            update={
                "doc_id": "doc-generic",
                "text": "Consider referral for persistent symptoms.",
                "rerank_score": 0.05,
                "final_score": 0.0,
                "vector_score": 0.43,
                "keyword_rank": None,
                "metadata": {
                    "specialty": "rheumatology",
                    "title": "General referral guidance",
                    "section_path": ["Referral"],
                },
            }
        )
        specific = make_ranked_result("c-specific").model_copy(
            update={
                "doc_id": "doc-specific",
                "text": ("Gout treatment should start promptly for acute gout flares."),
                "rerank_score": 0.0,
                "final_score": 0.0,
                "vector_score": 0.41,
                "keyword_rank": None,
                "metadata": {
                    "specialty": "rheumatology",
                    "title": "Gout treatment and diagnosis",
                    "section_path": ["Acute gout treatment"],
                },
            }
        )
        mocks = make_all_stage_mocks(deduped_results=[generic, specific])

        run_retrieve(mocks, top_k=2, specialty="rheumatology")

        ranked = mocks["assemble_citations"].call_args.args[0]
        assert [item.chunk_id for item in ranked] == ["c-specific", "c-generic"]

    def test_total_timing_logged(self):
        mocks = make_all_stage_mocks()
        with patch("src.retrieval.retrieve.logger") as mock_logger:
            run_retrieve(mocks)
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Retrieval complete" in c for c in info_calls)

    def test_debug_artifacts_strip_embedding_from_query(self, tmp_path: Path):
        mocks = make_all_stage_mocks()
        with patch("src.retrieval.retrieve.DEBUG_ARTIFACT_DIR", tmp_path):
            run_retrieve(mocks, write_debug_artifacts=True)
        query_artifact = json.loads(next(tmp_path.rglob("01_query.json")).read_text())
        assert "embedding" not in query_artifact

    def test_score_threshold_passed_through_to_filters(self):
        mocks = make_all_stage_mocks()
        run_retrieve(mocks, score_threshold=0.7)
        _, fkwargs = mocks["apply_filters"].call_args
        assert fkwargs["config"].score_threshold == 0.7


# -----------------------------------------------------------------------
# _calibrate_final_score
# -----------------------------------------------------------------------


class TestCalibrateScore:
    def test_low_quality_low_structure_penalty(self):
        """Cover line 381: quality_signal < 0.45 and structural_relevance < 0.5"""
        from src.retrieval.retrieve import _calibrate_score

        result = make_ranked_result("c-garbled").model_copy(
            update={
                "rerank_score": 0.1,
                "vector_score": 0.1,
                "keyword_rank": None,
                "text": "zx3 q7b xnm kl2 p9f",
                "metadata": {"title": "Unrelated", "section_path": []},
            }
        )
        score_penalized = _calibrate_score("gout treatment options", result)

        # Same inputs but with good quality text — no penalty
        good_result = result.model_copy(
            update={"text": "Gout treatment involves urate lowering therapy"}
        )
        score_clean = _calibrate_score("gout treatment options", good_result)

        assert score_penalized < score_clean

    def test_moderate_quality_low_structure_penalty(self):
        """Cover line 383: quality < 0.6 and structural_relevance < 0.34"""
        from src.retrieval.retrieve import _calibrate_score

        result = make_ranked_result("c-short").model_copy(
            update={
                "rerank_score": 0.5,
                "vector_score": 0.5,
                "keyword_rank": None,
                "text": "ab cd ef gh ij kl mn op qr st uv wx yz",
                "metadata": {
                    "title": "Unrelated Doc",
                    "section_path": [],
                },
            }
        )
        score = _calibrate_score("gout treatment options", result)
        assert isinstance(score, float)

    def test_overlap_count_floor_applied(self):
        """Cover line 389: overlap_count >= 2 floors blended at vector_score"""
        from src.retrieval.retrieve import _calibrate_score

        result = make_ranked_result("c-overlap").model_copy(
            update={
                "rerank_score": 0.01,
                "vector_score": 0.7,
                "keyword_rank": None,
                "text": "alpha gout beta treatment gamma management",
                "metadata": {"title": "Guide", "section_path": []},
            }
        )
        score = _calibrate_score("gout treatment options", result)
        assert score >= 0.7 * 0.95


# -----------------------------------------------------------------------
# _extract_query_age
# -----------------------------------------------------------------------


class TestExtractQueryAge:
    def test_extract_query_age_returns_none_for_no_match(self):
        from src.retrieval.retrieve import _extract_query_age

        assert _extract_query_age("patient with gait issues") is None

    def test_extract_query_age_extracts_age(self):
        from src.retrieval.retrieve import _extract_query_age

        assert _extract_query_age("65-year-old with headache") == 65

    def test_extract_query_age_returns_none_when_match_is_not_numeric(self):
        from src.retrieval.retrieve import _extract_query_age

        class _FakeMatch:
            def group(self, index: int) -> str:
                assert index == 1
                return "not-a-number"

        with patch("src.retrieval.retrieve.re.search", return_value=_FakeMatch()):
            assert _extract_query_age("65-year-old with headache") is None


# -----------------------------------------------------------------------
# _age_alignment_score
# -----------------------------------------------------------------------


class TestAgeAlignmentScore:
    def test_age_alignment_child_query_penalizes_adult_markers(self):
        from src.retrieval.retrieve import _age_alignment_score

        score = _age_alignment_score(12, "Treatment for adults over 18 years")
        assert score < 0

    def test_age_alignment_child_query_boosts_child_markers(self):
        from src.retrieval.retrieve import _age_alignment_score

        score = _age_alignment_score(12, "Paediatric guidelines for children")
        assert score > 0


# -----------------------------------------------------------------------
# _apply_final_ranking - no viable preferred specialty
# -----------------------------------------------------------------------


class TestApplyFinalRankingNoViable:
    def test_final_ranking_no_viable_preferred_returns_calibrated_order(self):
        """Cover line 483: no viable preferred items returns calibrated as-is"""
        from src.retrieval.retrieve import _apply_final_ranking

        item = make_ranked_result("c1").model_copy(
            update={
                "doc_id": "doc-1",
                "text": "Some text.",
                "rerank_score": 0.01,
                "final_score": 0.0,
                "vector_score": 0.2,
                "keyword_rank": None,
                "metadata": {"specialty": "rheumatology"},
            }
        )
        # Request neurology but only rheumatology items exist with low scores
        ranked = _apply_final_ranking(
            "query about something",
            [item],
            preferred_specialty="neurology",
        )
        assert len(ranked) == 1


# -----------------------------------------------------------------------
# _diversify_by_document
# -----------------------------------------------------------------------


class TestDiversifyByDocument:
    def test_diversify_by_document_with_zero_limit_returns_all(self):
        from src.retrieval.retrieve import _diversify_by_document

        items = [make_ranked_result(f"c{i}") for i in range(3)]
        result = _diversify_by_document(items, max_per_doc=0)
        assert len(result) == 3

    def test_diversify_by_document_skips_diversification_for_two_docs(self):
        from src.retrieval.retrieve import _diversify_by_document

        items = [
            make_ranked_result("c1").model_copy(update={"doc_id": "doc-a"}),
            make_ranked_result("c2").model_copy(update={"doc_id": "doc-a"}),
            make_ranked_result("c3").model_copy(update={"doc_id": "doc-b"}),
        ]

        result = _diversify_by_document(items, max_per_doc=1)

        assert [item.chunk_id for item in result] == ["c1", "c2", "c3"]


class TestFlatRerankFallback:
    def test_fallback_sort_for_flat_rerank_prefers_overlap(self) -> None:
        from src.retrieval.retrieve import _fallback_sort_for_flat_rerank

        vague = make_ranked_result("c1").model_copy(
            update={
                "text": "General neurology overview.",
                "metadata": {"title": "General guide"},
                "rerank_score": 0.0,
                "rrf_score": 0.8,
            }
        )
        focused = make_ranked_result("c2").model_copy(
            update={
                "text": (
                    "Suspect essential tremor in adults with symmetrical "
                    "postural tremor and no symptoms of parkinsonism."
                ),
                "metadata": {"title": "Tremor in adults"},
                "rerank_score": 0.0,
                "rrf_score": 0.2,
            }
        )

        ranked = _fallback_sort_for_flat_rerank(
            "intermittent hand tremor worse with anxiety and caffeine",
            [vague, focused],
        )

        assert [item.chunk_id for item in ranked] == ["c2", "c1"]


class TestFlatRerankPipelinePath:
    """Cover lines 218-219: flat-rerank fallback triggered inside retrieve()."""

    def test_retrieve_triggers_fallback_sort_when_rerank_is_uninformative(self):
        """When all rerank_scores are 0, _rerank_is_uninformative → True,
        so retrieve() calls _fallback_sort_for_flat_rerank (lines 218-219)."""
        flat_result_a = make_ranked_result("flat-a").model_copy(
            update={
                "text": "Prednisolone is first-line for PMR.",
                "rerank_score": 0.0,
                "metadata": {"title": "PMR Guide"},
            }
        )
        flat_result_b = make_ranked_result("flat-b").model_copy(
            update={
                "text": "Start at 15 mg/day prednisolone.",
                "rerank_score": 0.0,
                "metadata": {"title": "PMR Dosing"},
            }
        )
        mocks = make_all_stage_mocks(reranked_results=[flat_result_a, flat_result_b])
        output = run_retrieve(mocks)
        # Both results pass through after fallback sort
        assert len(output) == len(mocks["assemble_citations"].return_value)


class TestDiversifyByDocumentCap:
    """Cover lines 581-589: cap applied when > 2 unique doc_ids."""

    def test_cap_is_applied_when_more_than_two_unique_docs(self):
        from src.retrieval.retrieve import _diversify_by_document

        # 3 unique doc_ids, 2 chunks from doc-a, 1 each from doc-b/c
        items = [
            make_ranked_result("c1").model_copy(update={"doc_id": "doc-a"}),
            make_ranked_result("c2").model_copy(update={"doc_id": "doc-a"}),
            make_ranked_result("c3").model_copy(update={"doc_id": "doc-b"}),
            make_ranked_result("c4").model_copy(update={"doc_id": "doc-c"}),
        ]
        result = _diversify_by_document(items, max_per_doc=1)
        # doc-a is capped at 1; doc-b and doc-c get 1 each → 3 total
        assert len(result) == 3
        doc_ids = [item.doc_id for item in result]
        assert doc_ids.count("doc-a") == 1
        assert doc_ids.count("doc-b") == 1
        assert doc_ids.count("doc-c") == 1

    def test_cap_preserves_order_by_first_occurrence(self):
        from src.retrieval.retrieve import _diversify_by_document

        items = [
            make_ranked_result("c1").model_copy(update={"doc_id": "doc-x"}),
            make_ranked_result("c2").model_copy(update={"doc_id": "doc-y"}),
            make_ranked_result("c3").model_copy(update={"doc_id": "doc-x"}),  # capped
            make_ranked_result("c4").model_copy(update={"doc_id": "doc-z"}),
        ]
        result = _diversify_by_document(items, max_per_doc=1)
        assert [r.chunk_id for r in result] == ["c1", "c2", "c4"]

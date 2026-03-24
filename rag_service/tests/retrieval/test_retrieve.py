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

    def test_document_diversification_limits_one_chunk_per_doc(self):
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
                    "Adalimumab is recommended in some settings after DMARD "
                    "failure."
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
        assert vkwargs["top_k"] == 40
        _, kkwargs = mocks["keyword_search"].call_args
        assert kkwargs["top_k"] == 40
        _, fkwargs = mocks["reciprocal_rank_fusion"].call_args
        assert fkwargs["top_k"] == 40
        _, rkwargs = mocks["rerank"].call_args
        assert rkwargs["top_k"] == 40

    def test_filters_passed_through_to_vector_and_keyword_search(self):
        mocks = make_all_stage_mocks()
        run_retrieve(
            mocks,
            specialty="rheumatology",
            source_name="NICE",
            doc_type="guideline",
        )
        _, vkwargs = mocks["vector_search"].call_args
        assert vkwargs["specialty"] is None
        assert vkwargs["source_name"] == "NICE"
        assert vkwargs["doc_type"] == "guideline"
        _, kkwargs = mocks["keyword_search"].call_args
        assert kkwargs["specialty"] is None
        assert kkwargs["source_name"] == "NICE"
        assert kkwargs["doc_type"] == "guideline"

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

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import routes
from src.api.schemas import QueryRequest, SearchResult
from src.main import app
from src.retrieval.citation import Citation, CitedResult


@pytest.mark.anyio
async def test_health_check_reports_cloud_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "_cloud_available", lambda: False)

    result = await routes.health_check()

    assert result["status"] == "ready"
    assert result["cloud_available"] is False


@pytest.mark.anyio
async def test_clinical_query_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "retrieve_chunks", boom)

    with pytest.raises(HTTPException, match="RAG inference error"):
        await routes.clinical_query(QueryRequest(query="q"))


@pytest.mark.anyio
async def test_clinical_query_returns_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda query, top_k, specialty: [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"filename": "guide.pdf"},
                "doc_id": "doc-1",
            }
        ],
    )

    result = await routes.clinical_query(QueryRequest(query="q"))

    assert result == [
        SearchResult(
            text="chunk",
            source="guide.pdf",
            score=0.9,
            doc_id="doc-1",
            metadata={"filename": "guide.pdf"},
        )
    ]


def test_augment_query_with_history_returns_original_for_non_followup() -> None:
    query = "Please summarize next steps."
    patient_context = {"conversation_history": "GP: prior baseline information"}

    augmented = routes._augment_query_with_history(query, patient_context)

    assert augmented == query


def test_augment_query_with_history_prefixes_latest_gp_line() -> None:
    query = "She now has new jaw pain and headache."
    patient_context = {
        "conversation_history": (
            "GP: Earlier concern\n"
            "Specialist: acknowledged\n"
            "GP: 70-year-old with PMR features and raised ESR"
        )
    }

    augmented = routes._augment_query_with_history(query, patient_context)

    assert augmented.startswith("70-year-old with PMR features and raised ESR\n")
    assert augmented.endswith(query)


def test_augment_query_with_history_returns_original_when_no_gp_lines() -> None:
    query = "She also has worsening weakness today."
    patient_context = {
        "conversation_history": "Specialist: prior note without GP-prefixed lines"
    }

    augmented = routes._augment_query_with_history(query, patient_context)

    assert augmented == query


@pytest.mark.anyio
async def test_fetch_document_rejects_paths_outside_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"pdf")
    monkeypatch.setattr(
        routes,
        "get_source_path_for_doc",
        lambda doc_id: str(outside_file),
    )

    with pytest.raises(HTTPException, match="Invalid document path"):
        await routes.fetch_document("doc-1")


@pytest.mark.anyio
async def test_fetch_document_returns_file_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    doc = tmp_path / "data" / "doc.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"pdf")
    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(routes, "get_source_path_for_doc", lambda doc_id: str(doc))

    response = await routes.fetch_document("doc-1")

    assert response.path == doc.resolve()


def test_ingest_guideline_wraps_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("RAG_ENV", "test")
    client = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(
        routes,
        "load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )

    def boom(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(routes, "run_ingestion", boom)

    response = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Ingestion error"


@pytest.mark.anyio
async def test_ingest_guideline_rejects_oversized_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(routes, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(
        routes,
        "load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )

    oversized_file = SimpleNamespace(
        filename="guide.pdf",
        size=(50 * 1024 * 1024) + 1,
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_guideline(oversized_file, "NICE")

    assert exc_info.value.status_code == 422
    assert "File too large" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_generate_clinical_answer_preserves_http_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [{}],
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "build_grounded_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HTTPException(status_code=418, detail="teapot")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.generate_clinical_answer(
            routes.AnswerRequest(query="q", stream=True)
        )

    assert exc_info.value.status_code == 418
    assert exc_info.value.detail == "teapot"


@pytest.mark.anyio
async def test_revise_clinical_answer_preserves_http_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [{}])
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "build_revision_prompt",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            HTTPException(status_code=422, detail="bad stream")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.revise_clinical_answer(
            routes.ReviseRequest(
                original_query="q",
                previous_answer="a",
                feedback="f",
                stream=True,
            )
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "bad stream"


@pytest.mark.anyio
async def test_revise_clinical_answer_returns_no_evidence_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [])
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: [],
    )

    response = await routes.revise_clinical_answer(
        routes.ReviseRequest(
            original_query="q",
            previous_answer="a",
            feedback="f",
            stream=False,
        )
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE


@pytest.mark.anyio
async def test_generate_clinical_answer_returns_no_evidence_for_empty_post_processed_answer(  # noqa: E501
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieved = [
        {
            "text": "Relevant chunk.",
            "score": 0.9,
            "metadata": {"title": "Guide"},
            "doc_id": "doc-1",
        }
    ]

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (
            "",
            citations,
        ),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", specialty="neurology", stream=False)
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert response.citations_retrieved


@pytest.mark.anyio
async def test_revise_clinical_answer_returns_no_evidence_for_empty_post_processed_answer(  # noqa: E501
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieved = [
        {
            "text": "Relevant chunk.",
            "score": 0.9,
            "metadata": {"title": "Guide"},
            "doc_id": "doc-1",
        }
    ]

    monkeypatch.setattr(
        routes, "retrieve_chunks", lambda query, top_k, specialty: retrieved
    )
    monkeypatch.setattr(
        routes, "filter_chunks", lambda query, retrieved, specialty=None: retrieved
    )
    monkeypatch.setattr(routes, "build_revision_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (
            "",
            citations,
        ),
    )

    response = await routes.revise_clinical_answer(
        routes.ReviseRequest(
            original_query="q",
            previous_answer="a",
            feedback="f",
            stream=False,
        )
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert response.citations_retrieved


def test_no_evidence_response_preserves_retrieved_citations() -> None:
    citations = [SearchResult(text="evidence", source="guide.pdf", score=0.9)]

    response = routes._no_evidence_response(
        False,
        citations_retrieved=citations,
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert response.citations_used == []
    assert response.citations == []
    assert response.citations_retrieved == citations


@pytest.mark.anyio
async def test_generate_clinical_answer_generic_exception_wrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lines 180-182: generic Exception handler in /answer endpoint."""

    def boom_retrieve(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: boom_retrieve(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.generate_clinical_answer(
            routes.AnswerRequest(query="q", stream=False)
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "RAG answer error"


@pytest.mark.anyio
async def test_generate_clinical_answer_uses_vector_fallback_when_rerank_is_weak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citation = Citation(
        title="Rheumatoid arthritis in adults: management",
        source_name="NICE",
        specialty="rheumatology",
        doc_type="guideline",
        section_path=["Referral"],
        section_title="Referral",
        page_start=6,
        page_end=6,
        source_url="https://example.com/ra",
        doc_id="doc-ra",
        chunk_id="chunk-ra",
        content_type="text",
    )
    result = CitedResult(
        chunk_id="chunk-ra",
        text=(
            "Refer for specialist opinion any adult with suspected persistent "
            "synovitis of undetermined cause. If investigations are ordered in "
            "primary care, they should not delay referral."
        ),
        rerank_score=0.01,
        final_score=0.58,
        rrf_score=0.2,
        vector_score=0.58,
        keyword_rank=0.1,
        citation=citation,
    )

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [routes.api_services._cited_result_to_chunk(result)],
    )

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query=(
                "What baseline blood tests and imaging should be completed "
                "prior to referral?"
            ),
            specialty="rheumatology",
            stream=False,
        )
    )

    assert response.answer.startswith("Answer [1]")
    assert len(response.citations_used) == 1


@pytest.mark.anyio
async def test_generate_clinical_answer_forwards_advanced_retrieval_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        captured.update(kwargs)
        return [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"title": "Guide"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "A"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="q",
            specialty="neurology",
            source_name="NICE",
            doc_type="guideline",
            score_threshold=0.42,
            expand_query=True,
            stream=False,
        )
    )

    assert response.answer == "A"
    assert response.citations_used == []
    assert captured["query"] == "q"
    assert captured["specialty"] == "neurology"
    assert captured["source_name"] == "NICE"
    assert captured["doc_type"] == "guideline"
    assert captured["score_threshold"] == 0.42
    assert captured["expand_query"] is True


@pytest.mark.anyio
async def test_generate_clinical_answer_keeps_uncited_low_risk_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieved = [
        {
            "text": "Tremor may worsen with stimulants and anxiety.",
            "score": 0.62,
            "metadata": {
                "title": "Benign tremor assessment",
                "source_url": "https://example.com/tremor",
            },
            "doc_id": "doc-1",
        }
    ]

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return (
            "Based on standard clinical practice: reduce caffeine, review "
            "reversible causes, and reassure if there are no red flags."
        )

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query=(
                "29-year-old with intermittent hand tremor worse with anxiety "
                "and caffeine. No rigidity, bradykinesia, or neurological "
                "deficit. What initial management is appropriate before referral?"
            ),
            specialty="neurology",
            stream=False,
        )
    )

    assert response.answer.startswith("Based on standard clinical practice:")
    assert response.citations_used == []
    assert response.citations_retrieved
    assert response.citations == []


@pytest.mark.anyio
async def test_generate_clinical_answer_falls_back_when_advanced_retriever_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    monkeypatch.delattr(routes.api_services, "retrieve_chunks_advanced", raising=False)

    def fake_basic(query: str, *, top_k: int, specialty: str | None):
        called.update({"query": query, "top_k": top_k, "specialty": specialty})
        return [
            {
                "text": "chunk",
                "score": 0.9,
                "metadata": {"title": "Guide"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes, "retrieve_chunks", fake_basic)
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args, **kwargs):
        return "A"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", top_k=3, specialty="neurology")
    )

    assert response.answer == "A"
    assert response.citations_used == []
    assert called == {"query": "q", "top_k": 3, "specialty": "neurology"}


@pytest.mark.anyio
async def test_generate_clinical_answer_refuses_source_echo_only_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieved = [
        {
            "text": "Migraine aura guidance.",
            "score": 0.9,
            "metadata": {"title": "Guide"},
            "doc_id": "doc-1",
        }
    ]

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: retrieved,
    )
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return (
            "[Source: [1] Headaches in over 12s] "
            "[Source: [2] Stroke and transient ischaemic attack in over 16s]"
        )

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="How can migraine aura be distinguished from TIA?",
            specialty="neurology",
            stream=False,
        )
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert response.citations_used == []


@pytest.mark.anyio
async def test_generate_clinical_answer_uses_canonical_query_when_it_scores_better(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    calls: list[str] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda query, specialty, allowed_specialties: "canonical query",
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        calls.append(str(kwargs["query"]))
        if kwargs["query"] == "canonical query":
            return [
                {
                    "text": "Persistent synovitis should be referred urgently.",
                    "score": 0.91,
                    "metadata": {"title": "Guide"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "Off-target context chunk.",
                "score": 0.1,
                "metadata": {"title": "Paper"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)

    def fake_filter(
        query_text: str,
        retrieved: list[dict[str, object]],
        specialty: str | None = None,
    ) -> list[dict[str, object]]:
        del specialty
        if query_text == query:
            return retrieved
        return retrieved

    monkeypatch.setattr(routes, "filter_chunks", fake_filter)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (
            answer,
            citations,
        ),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert calls == [query, "canonical query"]


@pytest.mark.anyio
async def test_generate_clinical_answer_keeps_original_query_when_canonical_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=False,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        calls.append(str(kwargs["query"]))
        return [
            {
                "text": "Relevant chunk.",
                "score": 0.9,
                "metadata": {"title": "Guide"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (
            answer,
            citations,
        ),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert calls == ["q"]


@pytest.mark.anyio
async def test_generate_clinical_answer_keeps_original_when_canonical_not_better(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    calls: list[str] = []

    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda query, specialty, allowed_specialties: "canonical query",
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        calls.append(str(kwargs["query"]))
        if kwargs["query"] == "canonical query":
            return [
                {
                    "text": "Canonical chunk.",
                    "score": 0.45,
                    "metadata": {"title": "Guide"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "Original chunk.",
                "score": 0.9,
                "metadata": {"title": "Guide"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(
        routes,
        "filter_chunks",
        lambda query, retrieved, specialty=None: retrieved,
    )
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)

    async def fake_generate_answer(*args: object, **kwargs: object) -> str:
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None, **kwargs: (
            answer,
            citations,
        ),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert calls == [query, "canonical query"]


def test_choose_retrieval_query_returns_original_when_canonical_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = routes.AnswerRequest(query="q", specialty="rheumatology", stream=False)
    monkeypatch.setattr(
        routes,
        "_retrieve_for_answer_request",
        lambda request, query: [{"text": "chunk", "score": 0.9}],
    )
    monkeypatch.setattr(
        routes,
        "_retrieval_quality",
        lambda query, retrieved, specialty=None: (retrieved, 0.9),
    )
    monkeypatch.setattr(
        routes,
        "retrieval_config",
        SimpleNamespace(
            retrieval_canonicalization_enabled=True,
            retrieval_canonicalization_specialties="rheumatology",
        ),
    )
    monkeypatch.setattr(
        routes,
        "build_canonical_retrieval_query",
        lambda query, specialty, allowed_specialties: None,
    )

    retrieval_query, retrieved = routes._choose_retrieval_query(request)

    assert retrieval_query == "q"
    assert retrieved == [{"text": "chunk", "score": 0.9}]


@pytest.mark.anyio
async def test_documents_health_returns_per_document_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover the /documents/health endpoint (lines 149-168)."""
    from datetime import datetime, timezone

    ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    class FakeCursor:
        def execute(self, sql: str) -> None:
            pass

        def fetchall(self) -> list[tuple[str, str, int, datetime]]:
            return [
                ("doc-1", "NICE", 5, ts),
                ("doc-2", "WHO", 3, None),
            ]

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            pass

    monkeypatch.setattr(routes.db_manager, "get_raw_connection", FakeConnection)

    result = await routes.documents_health()

    assert result == [
        {
            "doc_id": "doc-1",
            "source_name": "NICE",
            "chunk_count": 5,
            "latest_ingestion": ts.isoformat(),
        },
        {
            "doc_id": "doc-2",
            "source_name": "WHO",
            "chunk_count": 3,
            "latest_ingestion": None,
        },
    ]


@pytest.mark.anyio
async def test_documents_health_closes_connection_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure the connection is closed even when the query raises."""
    closed: list[bool] = []

    class FailCursor:
        def execute(self, sql: str) -> None:
            raise RuntimeError("db error")

        def __enter__(self) -> FailCursor:
            return self

        def __exit__(self, *args: object) -> None:
            pass

    class FakeConnection:
        def cursor(self) -> FailCursor:
            return FailCursor()

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(routes.db_manager, "get_raw_connection", FakeConnection)

    with pytest.raises(RuntimeError, match="db error"):
        await routes.documents_health()

    assert closed == [True]


def test_cloud_available_exception_fallback_with_valid_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover lines 65-68: _cloud_available falls back when configured check raises."""
    import src.config.llm as llm_mod

    fake_config = SimpleNamespace(
        base_url="https://api.realhost.com/v1",
        api_key="sk-test-key",
    )
    monkeypatch.setattr(routes, "cloud_llm_config", fake_config)

    def _boom(_cfg: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(llm_mod, "cloud_llm_is_configured", _boom)

    assert routes._cloud_available() is True


def test_cloud_available_exception_fallback_rejects_example_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover lines 65-68: _cloud_available rejects example.invalid in fallback."""
    import src.config.llm as llm_mod

    fake_config = SimpleNamespace(
        base_url="https://example.invalid/v1",
        api_key="sk-test-key",
    )
    monkeypatch.setattr(routes, "cloud_llm_config", fake_config)

    def _boom(_cfg: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(llm_mod, "cloud_llm_is_configured", _boom)

    assert routes._cloud_available() is False

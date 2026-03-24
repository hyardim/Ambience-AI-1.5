from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import routes
from src.api.schemas import QueryRequest, SearchResult
from src.main import app


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
        lambda **kwargs: [
            {
                "text": "supported chunk",
                "score": 0.9,
                "metadata": {"source_url": "https://example.com/guideline"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
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
    monkeypatch.setattr(
        routes,
        "retrieve_chunks",
        lambda query, top_k, specialty: [
            {
                "text": "supported chunk",
                "score": 0.9,
                "metadata": {"source_url": "https://example.com/guideline"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
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
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: [])

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
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
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
        lambda answer, citations, strip_references, query=None: (answer, []),
    )

    await routes.generate_clinical_answer(
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

    assert captured["query"] == "q"
    assert captured["specialty"] == "neurology"
    assert captured["source_name"] == "NICE"
    assert captured["doc_type"] == "guideline"
    assert captured["score_threshold"] == 0.42
    assert captured["expand_query"] is True


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
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
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
        lambda answer, citations, strip_references, query=None: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", top_k=3, specialty="neurology")
    )

    assert response.answer == "A"
    assert called == {"query": "q", "top_k": 3, "specialty": "neurology"}


@pytest.mark.anyio
async def test_generate_clinical_answer_prefers_guideline_retrieval_when_usable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_type_calls: list[str | None] = []

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        doc_type = kwargs.get("doc_type")
        doc_type_calls.append(doc_type if isinstance(doc_type, str) else None)
        if doc_type == "guideline":
            return [
                {
                    "text": (
                        "Refer urgently via nephrology pathway for lupus nephritis."
                    ),
                    "score": 0.9,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {
                        "title": "Guideline",
                        "source_url": "https://example.com/guideline",
                    },
                    "doc_id": "doc-g",
                }
            ]
        return [
            {
                "text": "Fallback chunk",
                "score": 0.9,
                "metadata": {"title": "Paper", "source_url": "https://example.com/paper"},
                "doc_id": "doc-p",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="SLE with proteinuria referral pathway",
            stream=False,
        )
    )

    assert response.answer == "Answer [1]"
    assert doc_type_calls == ["guideline"]


@pytest.mark.anyio
async def test_generate_clinical_answer_falls_back_to_all_docs_when_guideline_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc_type_calls: list[str | None] = []

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        doc_type = kwargs.get("doc_type")
        doc_type_calls.append(doc_type if isinstance(doc_type, str) else None)
        if doc_type == "guideline":
            return []
        return [
            {
                "text": "Refer urgently via nephrology pathway.",
                "score": 0.9,
                "metadata": {"title": "Paper", "source_url": "https://example.com/paper"},
                "doc_id": "doc-p",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )
    monkeypatch.setattr(routes, "log_route_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query="SLE with proteinuria referral pathway",
            stream=False,
        )
    )

    assert response.answer == "Answer [1]"
    assert doc_type_calls == ["guideline", None]


@pytest.mark.anyio
async def test_generate_clinical_answer_no_evidence_for_low_score_high_precision_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "weakly related chunk",
                "score": 0.01,
                "metadata": {"source_url": "https://example.com/doc"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(
            query=(
                "What baseline blood tests and imaging should be completed prior "
                "to referral?"
            ),
            stream=False,
        )
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE


@pytest.mark.anyio
async def test_generate_clinical_answer_uses_canonical_pass_when_primary_is_weak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    canonical_query = "canonical persistent synovitis retrieval query"
    prompt_chunks: dict[str, object] = {}
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

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
        lambda **kwargs: canonical_query,
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        if kwargs["query"] == canonical_query:
            return [
                {
                    "text": "Refer urgently for suspected persistent synovitis.",
                    "score": 0.9,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {"source_url": "https://example.com/guideline"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "Off-target contextual chunk.",
                "score": 0.001,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    def fake_build_grounded_prompt(*args: object, **kwargs: object) -> str:
        prompt_chunks["chunks"] = args[1]
        return "p"

    monkeypatch.setattr(routes, "build_grounded_prompt", fake_build_grounded_prompt)
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert prompt_chunks["chunks"][0]["text"] == (
        "Refer urgently for suspected persistent synovitis."
    )
    assert telemetry_calls
    _, selected_call = telemetry_calls[-1]
    assert selected_call["canonicalization_triggered"] is True
    assert selected_call["selected_retrieval_pass"] == "canonical"


@pytest.mark.anyio
async def test_generate_clinical_answer_both_weak_passes_return_no_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    canonical_query = "canonical persistent synovitis retrieval query"
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

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
        lambda **kwargs: canonical_query,
    )

    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [
            {
                "text": "Weak context only.",
                "score": 0.001,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == routes.NO_EVIDENCE_RESPONSE
    assert telemetry_calls
    _, fallback_call = telemetry_calls[-1]
    assert fallback_call["outcome"] == "fallback"
    assert fallback_call["fallback_reason"] == "low_confidence_retrieval"


@pytest.mark.anyio
async def test_canonical_pass_selected_for_weak_primary_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = (
        "35-year-old with intermittent joint swelling in knees and wrists over "
        "4 months. CRP mildly raised. No clear diagnosis. What baseline blood "
        "tests and imaging should be completed prior to referral?"
    )
    canonical_query = "canonical persistent synovitis retrieval query"
    telemetry_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

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
        lambda **kwargs: canonical_query,
    )

    def fake_advanced(**kwargs: object) -> list[dict[str, object]]:
        if kwargs["query"] == canonical_query:
            return [
                {
                    "text": "Refer urgently for suspected persistent synovitis.",
                    "score": 0.9,
                    "section_path": "Recommendations > Referral pathway",
                    "metadata": {"source_url": "https://example.com/guideline"},
                    "doc_id": "doc-2",
                }
            ]
        return [
            {
                "text": "Contextual rheumatology discussion paragraph.",
                "score": 0.56,
                "section_path": "Discussion",
                "metadata": {"source_url": "https://example.com/paper"},
                "doc_id": "doc-1",
            }
        ]

    monkeypatch.setattr(routes.api_services, "retrieve_chunks_advanced", fake_advanced)
    monkeypatch.setattr(routes, "filter_chunks", lambda query, retrieved: retrieved)
    monkeypatch.setattr(routes, "build_grounded_prompt", lambda *args, **kwargs: "p")
    monkeypatch.setattr(
        routes,
        "select_generation_provider",
        lambda **kwargs: SimpleNamespace(
            provider="local", score=0.9, threshold=0.5, reasons=()
        ),
    )

    def fake_log(*args: object, **kwargs: object) -> None:
        telemetry_calls.append((args, kwargs))

    monkeypatch.setattr(routes, "log_route_decision", fake_log)

    async def fake_generate_answer(*args, **kwargs):
        return "Answer [1]"

    monkeypatch.setattr(routes, "generate_answer", fake_generate_answer)
    monkeypatch.setattr(
        routes,
        "extract_citation_results",
        lambda answer, citations, strip_references, query=None: (answer, citations),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query=query, specialty="rheumatology", stream=False)
    )

    assert response.answer == "Answer [1]"
    assert telemetry_calls
    _, selected_call = telemetry_calls[-1]
    assert selected_call["canonicalization_triggered"] is True
    assert selected_call["selected_retrieval_pass"] == "canonical"


def test_should_reject_for_low_confidence_high_precision_nondirective_section() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    top_chunk = {
        "text": "ESR and CRP can be raised in SLE and infection contexts.",
        "score": 0.069,
        "section_path": "D > Rationale",
    }

    assert routes._should_reject_for_low_confidence(query, top_chunk) is True


def test_low_confidence_gate_keeps_high_precision_directive_section() -> None:
    query = (
        "What baseline blood tests and imaging should be completed prior to referral?"
    )
    top_chunk = {
        "text": (
            "Baseline blood tests include ESR and CRP. Complete imaging before "
            "referral using the referral pathway recommendations."
        ),
        "score": 0.069,
        "section_path": "Recommendations > Referral pathway",
    }

    assert routes._should_reject_for_low_confidence(query, top_chunk) is False


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

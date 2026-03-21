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
async def test_generate_clinical_answer_preserves_http_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [{}],
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
    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [{}])
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
        lambda answer, citations, strip_references: (answer, []),
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
        lambda answer, citations, strip_references: (answer, []),
    )

    response = await routes.generate_clinical_answer(
        routes.AnswerRequest(query="q", top_k=3, specialty="neurology")
    )

    assert response.answer == "A"
    assert called == {"query": "q", "top_k": 3, "specialty": "neurology"}


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

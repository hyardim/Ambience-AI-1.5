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

    with pytest.raises(HTTPException, match="RAG Inference Error: boom"):
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
    assert response.json()["detail"] == "Ingestion error: unexpected"


@pytest.mark.anyio
async def test_generate_clinical_answer_preserves_http_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "retrieve_chunks", lambda query, top_k, specialty: [{}])
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

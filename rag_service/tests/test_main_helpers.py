from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.main as main


@pytest.mark.anyio
async def test_clinical_query_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "retrieve_chunks", boom)

    with pytest.raises(HTTPException, match="RAG Inference Error: boom"):
        await main.clinical_query(main.QueryRequest(query="q"))


@pytest.mark.anyio
async def test_clinical_query_returns_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
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

    result = await main.clinical_query(main.QueryRequest(query="q"))

    assert result == [
        main.SearchResult(
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
        main, "get_source_path_for_doc", lambda doc_id: str(outside_file)
    )

    with pytest.raises(HTTPException, match="Invalid document path"):
        await main.fetch_document("doc-1")


@pytest.mark.anyio
async def test_fetch_document_returns_file_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    doc = tmp_path / "data" / "doc.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"pdf")
    monkeypatch.setattr(main, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(main, "get_source_path_for_doc", lambda doc_id: str(doc))

    response = await main.fetch_document("doc-1")

    assert response.path == doc.resolve()


def test_ingest_guideline_wraps_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = TestClient(main.app, raise_server_exceptions=False)
    monkeypatch.setattr(main, "path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(
        main,
        "load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )

    def boom(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(main, "run_ingestion", boom)

    response = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Ingestion error: unexpected"

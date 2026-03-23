from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import src.main as main


def test_main_exports_clinical_app() -> None:
    from src.api.app import app

    assert main.app is app


def test_main_reexports_query_model() -> None:
    payload = main.QueryRequest(query="q", top_k=2)

    assert payload.query == "q"
    assert payload.top_k == 2


def test_main_reexports_public_helpers() -> None:
    assert callable(main.retrieve_chunks)
    assert callable(main.streaming_generator)


@pytest.mark.anyio
async def test_main_fetch_document_reexport(tmp_path: Path) -> None:
    routes = importlib.import_module("src.api.routes")

    doc = tmp_path / "data" / "doc.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"pdf")

    original_path_config = routes.path_config
    original_get_source = routes.get_source_path_for_doc
    routes.path_config = type("PathConfig", (), {"root": tmp_path})()
    routes.get_source_path_for_doc = lambda doc_id: str(doc)
    try:
        response = await main.fetch_document("doc-1")
    finally:
        routes.path_config = original_path_config
        routes.get_source_path_for_doc = original_get_source

    assert response.path == doc.resolve()

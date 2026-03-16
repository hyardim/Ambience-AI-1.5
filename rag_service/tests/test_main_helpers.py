from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import src.main as main


@pytest.fixture(autouse=True)
def clear_embedding_caches() -> None:
    main.get_embedding_model.cache_clear()
    main.get_embedding_dimension.cache_clear()


def test_ensure_schema_initializes_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_embedding_dimension", lambda: 384)
    called: list[int] = []
    monkeypatch.setattr(main, "init_db", lambda vector_dim: called.append(vector_dim))

    main.ensure_schema()

    assert called == [384]


def test_ensure_schema_logs_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "get_embedding_dimension", lambda: 384)

    def boom(vector_dim: int) -> None:
        raise RuntimeError(f"bad dim {vector_dim}")

    monkeypatch.setattr(main, "init_db", boom)

    main.ensure_schema()


@pytest.mark.anyio
async def test_warmup_ollama_cloud_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "FORCE_CLOUD_LLM", True)
    calls: list[str] = []

    async def fake_warmup(provider: str = "local") -> None:
        calls.append(provider)

    monkeypatch.setattr(main, "warmup_model", fake_warmup)

    await main.warmup_ollama()

    assert calls == ["cloud"]


@pytest.mark.anyio
async def test_warmup_ollama_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "FORCE_CLOUD_LLM", False)
    calls: list[str] = []

    async def fake_warmup(provider: str = "local") -> None:
        calls.append(provider)

    monkeypatch.setattr(main, "warmup_model", fake_warmup)

    await main.warmup_ollama()

    assert calls == ["local"]


def test_get_embedding_model_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_load_embedder() -> object:
        calls.append("load")
        return object()

    monkeypatch.setattr(main, "load_embedder", fake_load_embedder)
    monkeypatch.setattr(main, "get_vector_dim", lambda model: 384)

    first = main.get_embedding_model()
    second = main.get_embedding_model()

    assert first is second
    assert calls == ["load"]


def test_get_embedding_dimension_uses_model(monkeypatch: pytest.MonkeyPatch) -> None:
    model = object()
    monkeypatch.setattr(main, "get_embedding_model", lambda: model)
    monkeypatch.setattr(
        main, "get_vector_dim", lambda loaded: 768 if loaded is model else 0
    )

    assert main.get_embedding_dimension() == 768


@pytest.mark.anyio
async def test_lifespan_runs_startup_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        main,
        "get_embedding_dimension",
        lambda: calls.append("dim") or 384,
    )
    monkeypatch.setattr(main, "ensure_schema", lambda: calls.append("schema"))

    async def fake_warmup() -> None:
        calls.append("warmup")

    monkeypatch.setattr(main, "warmup_ollama", fake_warmup)

    async with main.lifespan(main.app):
        calls.append("inside")

    assert calls == ["dim", "schema", "warmup", "inside"]


def test_extract_citation_results_can_strip_references() -> None:
    citations = [
        main.SearchResult(text="A", source="S", score=0.9),
        main.SearchResult(text="B", source="S", score=0.8),
    ]

    answer, used = main._extract_citation_results(
        "Use [2]\n\nReferences: ignored",
        citations,
        strip_references=True,
    )

    assert answer == "Use [1]"
    assert used == [citations[1]]


def test_parse_citation_group_skips_invalid_values() -> None:
    assert main._parse_citation_group("1, x, 5-a") == [1]


@pytest.mark.anyio
async def test_streaming_generator_uses_generate_answer_for_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate_answer(
        prompt: str,
        max_tokens: int | None = None,
        provider: str = "local",
    ) -> str:
        assert provider == "cloud"
        return "Cloud answer [1]"

    monkeypatch.setattr(main, "generate_answer", fake_generate_answer)
    citations = [main.SearchResult(text="A", source="S", score=0.9)]

    lines = []
    async for line in main._streaming_generator(
        "prompt",
        64,
        citations,
        provider="cloud",
    ):
        lines.append(line)

    assert len(lines) == 1
    assert '"type": "done"' in lines[0]


def test_filter_chunks_drops_low_quality_hits() -> None:
    kept = {
        "text": "migraine treatment guidance",
        "score": 0.9,
        "metadata": {"source_path": "/tmp/doc.pdf"},
    }
    dropped = {
        "text": "supplementary material",
        "score": 0.1,
        "metadata": {},
    }

    filtered = main._filter_chunks("migraine treatment", [kept, dropped])

    assert filtered == [kept]


@pytest.mark.anyio
async def test_clinical_query_wraps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "_retrieve_chunks", boom)

    with pytest.raises(HTTPException, match="RAG Inference Error: boom"):
        await main.clinical_query(main.QueryRequest(query="q"))


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

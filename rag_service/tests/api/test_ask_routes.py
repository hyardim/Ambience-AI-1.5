from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import ask_routes as ask_routes_module
from src.api.app import create_app
from src.api.schemas import AnswerResponse, SearchResult
from src.generation.prompts import ACTIVE_PROMPT
from src.retrieval.query import RetrievalError


def _make_response() -> AnswerResponse:
    return AnswerResponse(
        answer="answer",
        citations_used=[],
        citations=[
            SearchResult(
                text="context",
                source="Guide",
                score=0.9,
                doc_id="doc-1",
                chunk_id="chunk-1",
                page_start=1,
                page_end=2,
                section_path="Intro",
                metadata={
                    "title": "Guide",
                    "source_name": "NICE",
                    "specialty": "Cardiology",
                    "source_url": "https://example.com",
                },
            )
        ],
        citations_retrieved=[
            SearchResult(
                text="context",
                source="Guide",
                score=0.9,
                doc_id="doc-1",
                chunk_id="chunk-1",
                page_start=1,
                page_end=2,
                section_path="Intro",
                metadata={
                    "title": "Guide",
                    "source_name": "NICE",
                    "specialty": "Cardiology",
                    "source_url": "https://example.com",
                },
            )
        ],
    )


def _client(monkeypatch) -> TestClient:
    def fake_retrieve(**kwargs):
        return [{"text": "context", "score": 0.9, "metadata": {}}]

    async def fake_generate(**kwargs):
        return _make_response()

    monkeypatch.setattr(
        ask_routes_module.api_services,
        "retrieve_chunks_advanced",
        fake_retrieve,
    )
    monkeypatch.setattr(
        ask_routes_module,
        "_generate_answer_from_retrieval",
        fake_generate,
    )
    app = create_app()
    return TestClient(app)


def test_ask_success(monkeypatch) -> None:
    client = _client(monkeypatch)

    resp = client.post(
        "/ask",
        json={"query": "q", "top_k": 3, "score_threshold": 0.2, "expand_query": True},
    )

    body = resp.json()
    assert resp.status_code == 200
    assert body["answer"] == "answer"
    assert body["query"] == "q"
    assert body["model"] == ACTIVE_PROMPT
    assert len(body["sources"]) == 1
    assert body["sources"][0]["rerank_score"] == 0.9
    assert body["sources"][0]["citation"]["title"] == "Guide"


def test_ask_retrieval_failure(monkeypatch) -> None:
    def boom_retrieve(**kwargs):
        raise RetrievalError(stage="S", query="q", message="fail")

    monkeypatch.setattr(
        ask_routes_module.api_services,
        "retrieve_chunks_advanced",
        boom_retrieve,
    )
    app = create_app()
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 502
    assert "Retrieval failed" in resp.json()["detail"]


def test_ask_generation_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        ask_routes_module.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [{"text": "context", "score": 0.9, "metadata": {}}],
    )

    async def boom_generate(**kwargs):
        raise HTTPException(status_code=500, detail="RAG answer error")

    monkeypatch.setattr(
        ask_routes_module,
        "_generate_answer_from_retrieval",
        boom_generate,
    )
    app = create_app()
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 502
    assert "Generation failed" in resp.json()["detail"]


def test_ask_unexpected_failure(monkeypatch) -> None:
    def boom_retrieve(**kwargs):
        raise RuntimeError("oops")

    monkeypatch.setattr(
        ask_routes_module.api_services,
        "retrieve_chunks_advanced",
        boom_retrieve,
    )
    app = create_app()
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


def test_ask_non_answer_response_type(monkeypatch) -> None:
    """Line 84: when response is not AnswerResponse type."""
    monkeypatch.setattr(
        ask_routes_module.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [{"text": "ctx", "score": 0.9, "metadata": {}}],
    )

    async def fake_generate(**kwargs):
        return {"unexpected": "dict"}

    monkeypatch.setattr(
        ask_routes_module,
        "_generate_answer_from_retrieval",
        fake_generate,
    )
    app = create_app()
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 502
    assert "Unexpected response type" in resp.json()["detail"]


def test_ask_reraises_non_rag_http_exception(monkeypatch) -> None:
    """Line 94: re-raise of non-500 HTTPException."""
    monkeypatch.setattr(
        ask_routes_module.api_services,
        "retrieve_chunks_advanced",
        lambda **kwargs: [{"text": "ctx", "score": 0.9, "metadata": {}}],
    )

    async def fake_generate(**kwargs):
        raise HTTPException(status_code=429, detail="Too many requests")

    monkeypatch.setattr(
        ask_routes_module,
        "_generate_answer_from_retrieval",
        fake_generate,
    )
    app = create_app()
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 429
    assert resp.json()["detail"] == "Too many requests"


def test_ingest_save_error(monkeypatch, tmp_path: Path) -> None:
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.routes.path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr("src.api.routes.load_sources", lambda path: {"NICE": {}})

    with patch.object(Path, "open", side_effect=OSError("disk full")):
        resp = client.post(
            "/ingest",
            files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
            data={"source_name": "NICE"},
        )

    assert resp.status_code == 500
    assert "disk full" in resp.json()["detail"]

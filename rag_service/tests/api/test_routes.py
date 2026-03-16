from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.ingestion.pipeline import PipelineError
from src.rag.generate import GenerationError, RAGResponse
from src.retrieval.citation import Citation, CitedResult
from src.retrieval.query import RetrievalError


def _make_response() -> RAGResponse:
    citation = Citation(
        title="Guide",
        source_name="NICE",
        specialty="Cardiology",
        doc_type="guideline",
        section_path=["Intro"],
        section_title="Intro",
        page_start=1,
        page_end=2,
        source_url="https://example.com",
        doc_id="doc-1",
        chunk_id="chunk-1",
        content_type="text",
    )
    cited = CitedResult(
        chunk_id="chunk-1",
        text="context",
        rerank_score=0.9,
        rrf_score=0.8,
        vector_score=0.7,
        keyword_rank=0.6,
        citation=citation,
    )
    return RAGResponse(answer="answer", sources=[cited], query="q", model="m")


def _client(monkeypatch) -> TestClient:
    app = create_app()

    def fake_ask(**kwargs):
        return _make_response()

    monkeypatch.setattr("src.api.routes.ask", fake_ask)
    return TestClient(app)


def test_health_endpoint(monkeypatch) -> None:
    client = _client(monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


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
    assert body["model"] == "m"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["rerank_score"] == 0.9
    assert body["sources"][0]["citation"]["title"] == "Guide"


def test_ask_retrieval_failure(monkeypatch) -> None:
    app = create_app()

    def boom(**kwargs):
        raise RetrievalError(stage="S", query="q", message="fail")

    monkeypatch.setattr("src.api.routes.ask", boom)
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 502
    assert "Retrieval failed" in resp.json()["detail"]


def test_ask_generation_failure(monkeypatch) -> None:
    app = create_app()

    def boom(**kwargs):
        raise GenerationError(query="q", message="gen fail")

    monkeypatch.setattr("src.api.routes.ask", boom)
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 502
    assert "Generation failed" in resp.json()["detail"]


def test_ask_unexpected_failure(monkeypatch) -> None:
    app = create_app()

    def boom(**kwargs):
        raise RuntimeError("oops")

    monkeypatch.setattr("src.api.routes.ask", boom)
    client = TestClient(app)

    resp = client.post("/ask", json={"query": "q"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


def test_ingest_success(monkeypatch, tmp_path: Path) -> None:
    app = create_app()
    client = TestClient(app)
    fake_path_config = SimpleNamespace(root=tmp_path)
    monkeypatch.setattr("src.api.routes.path_config", fake_path_config)
    monkeypatch.setattr(
        "src.api.routes.load_sources",
        lambda path: {"NICE": {"specialty": "neurology"}},
    )
    monkeypatch.setattr(
        "src.api.routes.run_ingestion",
        lambda **kwargs: {
            "files_scanned": 1,
            "files_succeeded": 1,
            "files_failed": 0,
            "total_chunks": 3,
            "embeddings_succeeded": 3,
            "embeddings_failed": 0,
            "db": {"inserted": 3, "updated": 0, "skipped": 0, "failed": 0},
        },
    )

    resp = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert resp.status_code == 200
    assert resp.json()["filename"] == "guide.pdf"


def test_ingest_rejects_non_pdf(monkeypatch, tmp_path: Path) -> None:
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.routes.path_config", SimpleNamespace(root=tmp_path))

    resp = client.post(
        "/ingest",
        files={"file": ("guide.txt", b"text", "text/plain")},
        data={"source_name": "NICE"},
    )

    assert resp.status_code == 422


def test_ingest_unknown_source(monkeypatch, tmp_path: Path) -> None:
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.routes.path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr("src.api.routes.load_sources", lambda path: {"NICE": {}})

    resp = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "BSR"},
    )

    assert resp.status_code == 422
    assert "Unknown source" in resp.json()["detail"]


def test_ingest_pipeline_error(monkeypatch, tmp_path: Path) -> None:
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.routes.path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr("src.api.routes.load_sources", lambda path: {"NICE": {}})

    def boom(**kwargs):
        raise PipelineError(stage="store", pdf_path="guide.pdf", message="failed")

    monkeypatch.setattr("src.api.routes.run_ingestion", boom)

    resp = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert resp.status_code == 500
    assert "Pipeline failed" in resp.json()["detail"]


def test_ingest_value_error(monkeypatch, tmp_path: Path) -> None:
    app = create_app()
    client = TestClient(app)
    monkeypatch.setattr("src.api.routes.path_config", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr("src.api.routes.load_sources", lambda path: {"NICE": {}})
    monkeypatch.setattr(
        "src.api.routes.run_ingestion",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("bad input")),
    )

    resp = client.post(
        "/ingest",
        files={"file": ("guide.pdf", b"%PDF", "application/pdf")},
        data={"source_name": "NICE"},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"] == "bad input"


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

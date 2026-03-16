from __future__ import annotations

import importlib
import sys
import types
from enum import Enum
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

_STUBBED_MODULES = [
    "pydantic_settings",
    "sentence_transformers",
    "torch",
    "pgvector",
    "pgvector.sqlalchemy",
    "pgvector.psycopg2",
    "psycopg2",
    "psycopg2.extras",
    "psycopg2.errors",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
    "sqlalchemy.engine",
    "tqdm",
    "nltk",
    "nltk.tokenize",
    "fitz",
    "src.config",
    "src.ingestion.embed",
    "src.ingestion.pipeline",
    "src.retrieval.vector_store",
    "src.generation.client",
    "src.generation.streaming",
    "src.generation.prompts",
    "src.jobs.retry",
    "src.orchestration.generate",
    "src.orchestration.pipeline",
    "src.retrieval.query",
    "src.api.services",
    "src.api.app",
    "src.api.routes",
    "src.api.ask_routes",
    "src.main",
]


def _make_stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


class _FakeSearchResult(dict):
    def model_dump(self) -> dict[str, object]:
        return dict(self)


def _fake_to_search_result(value: dict[str, object]) -> _FakeSearchResult:
    metadata = value.get("metadata") or {}
    source = "Unknown Source"
    if isinstance(metadata, dict):
        source = (
            metadata.get("title")
            or metadata.get("source_name")
            or metadata.get("filename")
            or metadata.get("source_path")
            or source
        )

    return _FakeSearchResult(
        {
            "text": value.get("text", ""),
            "source": source,
            "score": value.get("score", 0.0),
            "doc_id": value.get("doc_id"),
            "doc_version": value.get("doc_version"),
            "chunk_id": value.get("chunk_id"),
            "chunk_index": value.get("chunk_index"),
            "content_type": value.get("content_type"),
            "page_start": value.get("page_start"),
            "page_end": value.get("page_end"),
            "section_path": value.get("section_path"),
            "creation_date": None,
            "publish_date": None,
            "last_updated_date": None,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
    )


def _install_stubs() -> None:
    ps = _make_stub("pydantic_settings")
    ps.BaseSettings = object
    ps.SettingsConfigDict = lambda **kw: None  # type: ignore[assignment]

    st = _make_stub("sentence_transformers")
    st.SentenceTransformer = MagicMock  # type: ignore[assignment]

    _make_stub("torch")
    _make_stub("pgvector")
    _make_stub("pgvector.sqlalchemy")
    _make_stub("pgvector.psycopg2")
    _make_stub("psycopg2")
    _make_stub("psycopg2.extras")
    _make_stub("psycopg2.errors")
    _make_stub("sqlalchemy")
    _make_stub("sqlalchemy.orm")
    _make_stub("sqlalchemy.pool")
    _make_stub("sqlalchemy.dialects")
    _make_stub("sqlalchemy.dialects.postgresql")
    _make_stub("sqlalchemy.engine")

    tqdm_mod = _make_stub("tqdm")
    tqdm_mod.tqdm = lambda it, **kw: it  # type: ignore[assignment]

    _make_stub("nltk")
    nltk_tok = _make_stub("nltk.tokenize")
    nltk_tok.sent_tokenize = lambda text, **kw: text.split(". ")  # type: ignore[assignment]

    _make_stub("fitz")
    ask_routes = _make_stub("src.api.ask_routes")
    ask_routes.router = APIRouter()  # type: ignore[attr-defined]

    fake_config = types.ModuleType("src.config")
    fake_config.db_config = types.SimpleNamespace(
        database_url="postgresql://admin:pw@localhost/test"
    )
    fake_config.local_llm_config = types.SimpleNamespace(
        base_url="http://localhost:11434",
        model="local",
        api_key="ollama",
        max_tokens=512,
        timeout_seconds=60.0,
    )
    fake_config.cloud_llm_config = types.SimpleNamespace(
        base_url="https://example.invalid/v1",
        model="cloud",
        api_key="",
        max_tokens=512,
        temperature=0.1,
        timeout_seconds=120.0,
    )
    fake_config.routing_config = types.SimpleNamespace(
        llm_route_threshold=0.65,
        force_cloud_llm=False,
        route_revisions_to_cloud=True,
        medium_prompt_chars=3500,
        long_prompt_chars=7000,
    )
    fake_config.retry_config = types.SimpleNamespace(
        redis_url="redis://localhost:6379/0",
        retry_enabled=True,
        retry_max_attempts=3,
        retry_backoff_seconds=10,
        retry_backoff_multiplier=2,
        retry_job_ttl_seconds=86400,
    )
    fake_config.logging_config = types.SimpleNamespace(
        log_level="INFO",
        log_file="logs/test.log",
    )
    fake_config.llm_config = types.SimpleNamespace(
        llm_base_url="http://localhost:11434/v1",
        llm_model="fake",
        llm_api_key="ollama",
        llm_max_tokens=512,
        llm_temperature=0.1,
        llm_timeout_seconds=120.0,
    )
    fake_config.generation_config = types.SimpleNamespace(
        ollama_base_url="http://localhost:11434",
        ollama_model="fake-local-model",
        ollama_max_tokens=512,
        ollama_timeout_seconds=60.0,
        prompt_variant="test",
    )
    path_config = MagicMock()
    path_config.root = Path("/app")
    fake_config.path_config = path_config
    sys.modules["src.config"] = fake_config

    for module_name in (
        "src.ingestion.embed",
        "src.ingestion.pipeline",
        "src.retrieval.vector_store",
        "src.generation.client",
        "src.generation.streaming",
        "src.generation.prompts",
        "src.jobs.retry",
        "src.orchestration.generate",
        "src.orchestration.pipeline",
        "src.retrieval.query",
        "src.api.services",
    ):
        _make_stub(module_name)

    sys.modules["src.ingestion.embed"].load_embedder = MagicMock(
        return_value=MagicMock()
    )
    sys.modules["src.ingestion.embed"].get_vector_dim = MagicMock(return_value=384)
    sys.modules["src.ingestion.embed"].embed_text = MagicMock(return_value=[[0.1]])

    sys.modules["src.retrieval.vector_store"].init_db = MagicMock()
    sys.modules["src.retrieval.vector_store"].search_similar_chunks = MagicMock(
        return_value=[]
    )
    sys.modules["src.retrieval.vector_store"].get_source_path_for_doc = MagicMock(
        return_value=None
    )

    class FakeModelGenerationError(RuntimeError):
        def __init__(self, message: str, retryable: bool) -> None:
            super().__init__(message)
            self.retryable = retryable

    sys.modules["src.generation.client"].ProviderName = Literal["local", "cloud"]
    sys.modules["src.generation.client"].ModelGenerationError = FakeModelGenerationError
    sys.modules["src.generation.client"].generate_answer = MagicMock()
    sys.modules["src.generation.client"].warmup_model = MagicMock()
    sys.modules["src.generation.client"]._auth_headers = MagicMock(return_value={})
    sys.modules["src.generation.client"]._extract_chat_completion_text = MagicMock(
        return_value="answer"
    )
    sys.modules["src.generation.streaming"].stream_generate = MagicMock()

    sys.modules["src.generation.prompts"].ACTIVE_PROMPT = "test"
    sys.modules["src.generation.prompts"].build_grounded_prompt = MagicMock(
        return_value="prompt"
    )
    sys.modules["src.generation.prompts"].build_revision_prompt = MagicMock(
        return_value="prompt"
    )

    class PipelineError(Exception):
        def __init__(self, stage: str, message: str) -> None:
            self.stage = stage
            self.message = message
            super().__init__(f"{stage}: {message}")

    sys.modules["src.ingestion.pipeline"].PipelineError = PipelineError
    sys.modules["src.ingestion.pipeline"].load_sources = MagicMock()
    sys.modules["src.ingestion.pipeline"].run_ingestion = MagicMock()

    retry_module = sys.modules["src.jobs.retry"]

    class FakeRetryJobStatus(str, Enum):
        QUEUED = "queued"

    retry_module.RetryJobStatus = FakeRetryJobStatus
    retry_module.create_retry_job = MagicMock(return_value=("job-1", "queued"))
    retry_module.get_retry_job = MagicMock(
        return_value={
            "job_id": "job-1",
            "status": "queued",
            "attempt_count": 1,
            "last_error": "",
            "created_at": "now",
            "updated_at": "now",
            "response": None,
        }
    )

    class FakeGenerationError(RuntimeError):
        pass

    fake_orchestration_generate = sys.modules["src.orchestration.generate"]
    fake_orchestration_generate.GenerationError = FakeGenerationError
    fake_orchestration_generate.RAGResponse = type("RAGResponse", (), {})

    fake_orchestration_pipeline = sys.modules["src.orchestration.pipeline"]
    fake_orchestration_pipeline.ask = MagicMock()

    class FakeRetrievalError(RuntimeError):
        pass

    fake_retrieval_query = sys.modules["src.retrieval.query"]
    fake_retrieval_query.RetrievalError = FakeRetrievalError

    fake_api_services = sys.modules["src.api.services"]
    fake_api_services.retrieve_chunks = MagicMock(return_value=[])
    fake_api_services.filter_chunks = MagicMock(
        side_effect=lambda _query, retrieved: retrieved
    )
    fake_api_services.log_route_decision = MagicMock()
    fake_api_services.to_search_result = MagicMock(side_effect=_fake_to_search_result)


def _restore_modules(originals: dict[str, types.ModuleType | None]) -> None:
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


@pytest.fixture()
def main_module():
    originals = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
    _install_stubs()
    sys.modules.pop("src.api.routes", None)
    sys.modules.pop("src.api.app", None)
    sys.modules.pop("src.api.ask_routes", None)
    sys.modules.pop("src.main", None)

    main = importlib.import_module("src.main")
    routes = importlib.import_module("src.api.routes")
    main.routes = routes
    try:
        yield main
    finally:
        sys.modules.pop("src.main", None)
        _restore_modules(originals)


@pytest.fixture()
def client(main_module):
    return TestClient(main_module.app, raise_server_exceptions=False)


def test_jobs_status_endpoint_returns_state(client):
    resp = client.get("/jobs/job-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job-1"
    assert body["status"] == "queued"


def test_health_endpoint_returns_runtime_settings(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["local_model"] == "local"


def test_jobs_status_returns_404_when_missing(client, main_module):
    main_module.routes.get_retry_job = MagicMock(return_value=None)

    resp = client.get("/jobs/missing")

    assert resp.status_code == 404


def test_answer_returns_202_on_retryable_failure(monkeypatch, client, main_module):
    main_module.routes.retrieve_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )

    async def fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise main_module.ModelGenerationError("transient", retryable=True)

    monkeypatch.setattr(main_module.routes, "generate_answer", fail)

    resp = client.post("/answer", json={"query": "headache", "top_k": 1})
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "job-1"


def test_answer_returns_done_stream_when_no_results(client, main_module):
    main_module.routes.retrieve_chunks = MagicMock(return_value=[])

    resp = client.post(
        "/answer",
        json={"query": "headache", "top_k": 1, "stream": True},
    )

    assert resp.status_code == 200
    assert '"type": "done"' in resp.text


def test_revise_returns_202_on_retryable_failure(monkeypatch, client, main_module):
    main_module.routes.retrieve_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )

    async def fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise main_module.ModelGenerationError("transient", retryable=True)

    monkeypatch.setattr(main_module.routes, "generate_answer", fail)

    resp = client.post(
        "/revise",
        json={
            "original_query": "headache",
            "previous_answer": "old",
            "feedback": "better",
            "top_k": 1,
        },
    )

    assert resp.status_code == 202
    assert resp.json()["job_id"] == "job-1"


def test_answer_returns_non_stream_empty_response(client, main_module):
    main_module.routes.retrieve_chunks = MagicMock(return_value=[])

    resp = client.post(
        "/answer",
        json={"query": "headache", "top_k": 1},
    )

    assert resp.status_code == 200
    assert "couldn't find any guideline passage" in resp.json()["answer"]


def test_answer_streams_with_results(client, main_module):
    main_module.routes.retrieve_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )

    resp = client.post(
        "/answer",
        json={"query": "headache", "top_k": 1, "stream": True},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")


def test_answer_non_retryable_generation_error_returns_500(
    monkeypatch,
    client,
    main_module,
):
    main_module.routes.retrieve_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )

    async def fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise main_module.ModelGenerationError("fatal", retryable=False)

    monkeypatch.setattr(main_module.routes, "generate_answer", fail)

    resp = client.post("/answer", json={"query": "headache", "top_k": 1})

    assert resp.status_code == 500


def test_answer_passes_specialty_to_similarity_search(client, main_module):
    search_mock = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )
    main_module.routes.retrieve_chunks = search_mock

    async def ok_answer(*args, **kwargs):  # noqa: ANN002, ANN003
        return "ok"

    main_module.routes.generate_answer = ok_answer

    resp = client.post(
        "/answer",
        json={"query": "headache", "top_k": 1, "specialty": "neurology"},
    )

    assert resp.status_code != 500
    search_mock.assert_called_once_with(
        "headache",
        top_k=1,
        specialty="neurology",
    )


def test_revise_passes_specialty_to_similarity_search(client, main_module):
    search_mock = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )
    main_module.routes.retrieve_chunks = search_mock

    async def ok_answer(*args, **kwargs):  # noqa: ANN002, ANN003
        return "ok"

    main_module.routes.generate_answer = ok_answer

    resp = client.post(
        "/revise",
        json={
            "original_query": "headache",
            "previous_answer": "old answer",
            "feedback": "be more specific",
            "top_k": 1,
            "specialty": "neurology",
        },
    )

    assert resp.status_code != 500
    search_mock.assert_called_once_with(
        "headache",
        top_k=1,
        specialty="neurology",
    )


def test_revise_streams_with_results(client, main_module):
    main_module.routes.retrieve_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )

    resp = client.post(
        "/revise",
        json={
            "original_query": "headache",
            "previous_answer": "old answer",
            "feedback": "be more specific",
            "top_k": 1,
            "stream": True,
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")


def test_revise_non_retryable_generation_error_returns_500(
    monkeypatch,
    client,
    main_module,
):
    main_module.routes.retrieve_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            },
        ]
    )

    async def fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise main_module.ModelGenerationError("fatal", retryable=False)

    monkeypatch.setattr(main_module.routes, "generate_answer", fail)

    resp = client.post(
        "/revise",
        json={
            "original_query": "headache",
            "previous_answer": "old answer",
            "feedback": "be more specific",
            "top_k": 1,
        },
    )

    assert resp.status_code == 500


def test_fetch_document_not_found(client, main_module):
    main_module.routes.get_source_path_for_doc = MagicMock(return_value=None)

    resp = client.get("/docs/doc-1")

    assert resp.status_code == 404


def test_fetch_document_missing_file(client, main_module, tmp_path):
    path = tmp_path / "data" / "missing.pdf"
    main_module.routes.path_config.root = tmp_path
    main_module.routes.get_source_path_for_doc = MagicMock(return_value=str(path))

    resp = client.get("/docs/doc-1")

    assert resp.status_code == 404
    assert "missing" in resp.json()["detail"].lower()


def test_fetch_document_success(client, main_module, tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    doc = data_root / "doc.pdf"
    doc.write_bytes(b"pdf")
    main_module.routes.path_config.root = tmp_path
    main_module.routes.get_source_path_for_doc = MagicMock(return_value=str(doc))

    resp = client.get("/docs/doc-1")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"

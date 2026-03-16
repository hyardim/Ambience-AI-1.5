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
    "src.generation.prompts",
    "src.jobs.retry",
    "src.api.app",
    "src.api.routes",
    "src.api.ask_routes",
    "src.main",
]


def _make_stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


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
    fake_config.DATABASE_URL = "postgresql://admin:pw@localhost/test"
    fake_config.OLLAMA_BASE_URL = "http://localhost:11434"
    fake_config.OLLAMA_MODEL = "fake"
    fake_config.OLLAMA_MAX_TOKENS = 512
    fake_config.CLOUD_LLM_MODEL = "cloud"
    fake_config.FORCE_CLOUD_LLM = False
    fake_config.LLM_MAX_TOKENS = 512
    fake_config.LLM_ROUTE_THRESHOLD = 0.65
    fake_config.LOCAL_LLM_MODEL = "local"
    fake_config.ROUTE_REVISIONS_TO_CLOUD = True
    fake_config.RETRY_ENABLED = True
    fake_config.REDIS_URL = "redis://localhost:6379/0"
    fake_config.RETRY_MAX_ATTEMPTS = 3
    fake_config.RETRY_BACKOFF_SECONDS = 10
    fake_config.RETRY_BACKOFF_MULTIPLIER = 2
    fake_config.RETRY_JOB_TTL_SECONDS = 86400
    path_config = MagicMock()
    path_config.root = Path("/app")
    fake_config.path_config = path_config
    sys.modules["src.config"] = fake_config

    for module_name in (
        "src.ingestion.embed",
        "src.ingestion.pipeline",
        "src.retrieval.vector_store",
        "src.generation.client",
        "src.generation.prompts",
        "src.jobs.retry",
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

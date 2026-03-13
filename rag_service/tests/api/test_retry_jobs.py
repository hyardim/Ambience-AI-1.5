from __future__ import annotations

import importlib
import sys
import types
from enum import Enum
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


_STUBBED_MODULES = [
    "pydantic_settings",
    "sentence_transformers",
    "torch",
    "pgvector",
    "pgvector.sqlalchemy",
    "psycopg2",
    "psycopg2.extras",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "sqlalchemy.dialects.postgresql",
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
    "src.retry_queue",
]


def _restore_modules(originals: dict[str, types.ModuleType | None]) -> None:
    for module_name, original in originals.items():
        if original is None:
            sys.modules.pop(module_name, None)
            if "." in module_name:
                parent_name, child_name = module_name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if parent is not None and hasattr(parent, child_name):
                    try:
                        delattr(parent, child_name)
                    except AttributeError:
                        pass
        else:
            sys.modules[module_name] = original


def _install_stubs() -> None:
    def make_stub(name: str) -> types.ModuleType:
        module = types.ModuleType(name)
        sys.modules[name] = module
        return module

    ps = make_stub("pydantic_settings")
    ps.BaseSettings = object
    ps.SettingsConfigDict = lambda **kw: None  # type: ignore[assignment]

    make_stub("sentence_transformers")
    make_stub("torch")
    make_stub("pgvector")
    make_stub("pgvector.sqlalchemy")
    make_stub("psycopg2")
    make_stub("psycopg2.extras")
    make_stub("sqlalchemy")
    make_stub("sqlalchemy.orm")
    make_stub("sqlalchemy.pool")
    make_stub("sqlalchemy.dialects")
    make_stub("sqlalchemy.dialects.postgresql")

    tqdm_mod = make_stub("tqdm")
    tqdm_mod.tqdm = lambda it, **kw: it  # type: ignore[assignment]

    make_stub("nltk")
    make_stub("nltk.tokenize")
    make_stub("fitz")

    fake_config = types.ModuleType("src.config")
    fake_config.DATABASE_URL = "postgresql://admin:pw@localhost/test"
    fake_config.OLLAMA_MODEL = "fake"
    fake_config.OLLAMA_MAX_TOKENS = 512
    fake_config.LLM_MAX_TOKENS = 512
    fake_config.FORCE_CLOUD_LLM = False
    fake_config.LLM_ROUTE_THRESHOLD = 0.65
    fake_config.ROUTE_REVISIONS_TO_CLOUD = True
    fake_config.LOCAL_LLM_MODEL = "local"
    fake_config.CLOUD_LLM_MODEL = "cloud"
    fake_config.RETRY_ENABLED = True
    fake_config.REDIS_URL = "redis://localhost:6379/0"
    fake_config.RETRY_BACKOFF_MULTIPLIER = 2
    fake_config.RETRY_BACKOFF_SECONDS = 10
    fake_config.RETRY_JOB_TTL_SECONDS = 86400
    fake_config.RETRY_MAX_ATTEMPTS = 3
    fake_config.path_config = MagicMock(root=MagicMock())
    sys.modules["src.config"] = fake_config

    for module_name in (
        "src.ingestion.embed",
        "src.ingestion.pipeline",
        "src.retrieval.vector_store",
        "src.generation.client",
        "src.generation.prompts",
        "src.retry_queue",
    ):
        sys.modules[module_name] = types.ModuleType(module_name)

    sys.modules["src.ingestion.embed"].load_embedder = MagicMock(return_value=MagicMock())
    sys.modules["src.ingestion.embed"].get_vector_dim = MagicMock(return_value=384)
    sys.modules["src.ingestion.embed"].embed_text = MagicMock(return_value=[[0.1]])

    sys.modules["src.retrieval.vector_store"].init_db = MagicMock()
    sys.modules["src.retrieval.vector_store"].search_similar_chunks = MagicMock(return_value=[])
    sys.modules["src.retrieval.vector_store"].get_source_path_for_doc = MagicMock(return_value=None)

    class FakeModelGenerationError(RuntimeError):
        def __init__(self, message: str, retryable: bool) -> None:
            super().__init__(message)
            self.retryable = retryable

    sys.modules["src.generation.client"].generate_answer = MagicMock()
    sys.modules["src.generation.client"].warmup_model = MagicMock()
    sys.modules["src.generation.client"].ModelGenerationError = FakeModelGenerationError

    sys.modules["src.generation.prompts"].ACTIVE_PROMPT = "test"
    sys.modules["src.generation.prompts"].build_grounded_prompt = MagicMock(return_value="prompt")
    sys.modules["src.generation.prompts"].build_revision_prompt = MagicMock(return_value="prompt")

    class PipelineError(Exception):
        def __init__(self, stage: str, message: str) -> None:
            self.stage = stage
            self.message = message
            super().__init__(f"{stage}: {message}")

    sys.modules["src.ingestion.pipeline"].PipelineError = PipelineError
    sys.modules["src.ingestion.pipeline"].load_sources = MagicMock()
    sys.modules["src.ingestion.pipeline"].run_ingestion = MagicMock()

    class FakeRetryJobStatus(str, Enum):
        QUEUED = "queued"

    retry_module = sys.modules["src.retry_queue"]
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


@pytest.fixture()
def main_module():
    originals = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
    _install_stubs()
    sys.modules.pop("src.main", None)

    main = importlib.import_module("src.main")
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


def test_answer_returns_202_on_retryable_failure(monkeypatch, client, main_module):
    main_module.search_similar_chunks = MagicMock(
        return_value=[
            {
                "text": "headache guidance",
                "score": 0.9,
                "metadata": {"source_path": "x"},
            }
        ]
    )

    async def fail(*args, **kwargs):  # noqa: ANN002, ANN003
        raise main_module.ModelGenerationError("transient", retryable=True)

    monkeypatch.setattr(main_module, "generate_answer", fail)

    resp = client.post("/answer", json={"query": "headache", "top_k": 1})
    assert resp.status_code == 202
    assert resp.json()["job_id"] == "job-1"

from __future__ import annotations

import importlib
import sys
import types
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
    "src.generation.router",
    "src.retry_queue",
]


def _restore_modules(originals: dict[str, types.ModuleType | None]) -> None:
    for module_name, original in originals.items():
        if original is None:
            sys.modules.pop(module_name, None)
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
    fake_config.CLOUD_LLM_MODEL = "cloud"
    fake_config.FORCE_CLOUD_LLM = False
    fake_config.LLM_MAX_TOKENS = 512
    fake_config.LLM_ROUTE_THRESHOLD = 0.65
    fake_config.LOCAL_LLM_MODEL = "local"
    fake_config.OLLAMA_BASE_URL = "http://localhost:11434"
    fake_config.OLLAMA_MODEL = "fake-model"
    fake_config.OLLAMA_MAX_TOKENS = 512
    fake_config.RETRY_ENABLED = False
    fake_config.path_config = MagicMock(root=MagicMock())
    sys.modules["src.config"] = fake_config

    for module_name in (
        "src.ingestion.embed",
        "src.ingestion.pipeline",
        "src.retrieval.vector_store",
        "src.generation.client",
        "src.generation.prompts",
        "src.generation.router",
        "src.retry_queue",
    ):
        sys.modules[module_name] = types.ModuleType(module_name)

    sys.modules["src.ingestion.embed"].load_embedder = MagicMock(
        return_value=MagicMock())
    sys.modules["src.ingestion.embed"].get_vector_dim = MagicMock(
        return_value=384)
    sys.modules["src.ingestion.embed"].embed_text = MagicMock(return_value=[
                                                              [0.1]])

    sys.modules["src.retrieval.vector_store"].init_db = MagicMock()
    sys.modules["src.retrieval.vector_store"].search_similar_chunks = MagicMock(
        return_value=[])
    sys.modules["src.retrieval.vector_store"].get_source_path_for_doc = MagicMock(
        return_value=None)

    class ModelGenerationError(Exception):
        retryable = False

    sys.modules["src.generation.client"].generate_answer = MagicMock(
        return_value="ok")
    sys.modules["src.generation.client"].warmup_model = MagicMock()
    sys.modules["src.generation.client"].ModelGenerationError = ModelGenerationError

    sys.modules["src.generation.prompts"].ACTIVE_PROMPT = "test"
    sys.modules["src.generation.prompts"].build_grounded_prompt = MagicMock(
        return_value="prompt")
    sys.modules["src.generation.prompts"].build_revision_prompt = MagicMock(
        return_value="prompt")

    sys.modules["src.generation.router"].select_generation_provider = MagicMock(
        return_value=MagicMock(provider="local", score=0.1,
                               threshold=0.65, reasons=())
    )

    sys.modules["src.retry_queue"].RetryJobStatus = str
    sys.modules["src.retry_queue"].create_retry_job = MagicMock(
        return_value=("job-1", "queued"))
    sys.modules["src.retry_queue"].get_retry_job = MagicMock(return_value=None)

    sys.modules["src.ingestion.pipeline"].PipelineError = Exception
    sys.modules["src.ingestion.pipeline"].load_sources = MagicMock(
        return_value={})
    sys.modules["src.ingestion.pipeline"].run_ingestion = MagicMock(
        return_value={})


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


def test_trigger_guideline_sync_returns_summary(client, main_module, monkeypatch) -> None:
    class FakeScheduler:
        async def trigger_once(self, **kwargs):  # noqa: ANN003
            return {
                "started_at": "start",
                "finished_at": "end",
                "summary": {
                    "discovered_count": 3,
                    "downloaded_new_count": 1,
                    "downloaded_updated_count": 1,
                    "skipped_unchanged_count": 1,
                    "ingest_succeeded_count": 2,
                    "ingest_failed_count": 0,
                    "errors": [],
                },
            }

        def status(self):
            return {
                "running": False,
                "enabled": False,
                "last_started_at": None,
                "last_finished_at": None,
                "last_error": None,
                "last_result": None,
            }

    monkeypatch.setattr(main_module, "sync_scheduler", FakeScheduler())

    resp = client.post(
        "/guidelines/sync",
        json={"source_names": ["NICE"], "dry_run": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["summary"]["discovered_count"] == 3


def test_guideline_sync_status_route(client, main_module, monkeypatch) -> None:
    class FakeScheduler:
        async def trigger_once(self, **kwargs):  # noqa: ANN003
            return {}

        def status(self):
            return {
                "running": True,
                "enabled": True,
                "last_started_at": "start",
                "last_finished_at": "end",
                "last_error": None,
                "last_result": {"summary": {"discovered_count": 1}},
            }

    monkeypatch.setattr(main_module, "sync_scheduler", FakeScheduler())

    resp = client.get("/guidelines/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert body["enabled"] is True
    assert body["last_result"]["summary"]["discovered_count"] == 1

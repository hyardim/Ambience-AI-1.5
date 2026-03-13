"""
Tests for POST /ingest on the RAG service (src/main.py).

This module loads src.main under temporary stubs for heavyweight dependencies.
Stubs are applied in a fixture and fully restored after this module's tests,
so other test modules are not affected.
"""

import importlib
import os
import sys
import types
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi.testclient import TestClient


_STUBBED_MODULE_NAMES = [
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


class _PipelineError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}: {message}")


class _ModelGenerationError(Exception):
    retryable = False


class _FakeRetryJobStatus(str, Enum):
    QUEUED = "queued"


PDF_BYTES = b"%PDF-1.4 fake pdf content"

FAKE_SOURCES = {
    "NICE": {"specialty": "rheumatology"},
    "BSR": {"specialty": "rheumatology"},
    "NICE_NEURO": {"specialty": "neurology"},
}

FAKE_REPORT = {
    "files_scanned": 1,
    "files_succeeded": 1,
    "files_failed": 0,
    "total_chunks": 45,
    "embeddings_succeeded": 45,
    "embeddings_failed": 0,
    "db": {"inserted": 45, "updated": 0, "skipped": 0, "failed": 0},
}


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
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    ps = make_stub("pydantic_settings")
    ps.BaseSettings = object
    ps.SettingsConfigDict = lambda **kw: None  # type: ignore[assignment]

    st = make_stub("sentence_transformers")
    st.SentenceTransformer = MagicMock  # type: ignore[assignment]

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
    fake_config.DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:pw@localhost/test")  # type: ignore[attr-defined]
    fake_config.CLOUD_LLM_MODEL = "fake-cloud-model"  # type: ignore[attr-defined]
    fake_config.FORCE_CLOUD_LLM = False  # type: ignore[attr-defined]
    fake_config.LLM_MAX_TOKENS = 512  # type: ignore[attr-defined]
    fake_config.LLM_ROUTE_THRESHOLD = 0.65  # type: ignore[attr-defined]
    fake_config.LOCAL_LLM_MODEL = "fake-local-model"  # type: ignore[attr-defined]
    fake_config.OLLAMA_BASE_URL = "http://localhost:11434"  # type: ignore[attr-defined]
    fake_config.OLLAMA_MODEL = "fake-model"  # type: ignore[attr-defined]
    fake_config.OLLAMA_MAX_TOKENS = 512  # type: ignore[attr-defined]
    fake_config.RETRY_ENABLED = False  # type: ignore[attr-defined]
    fake_config.REDIS_URL = "redis://localhost:6379/0"  # type: ignore[attr-defined]
    fake_config.RETRY_MAX_ATTEMPTS = 3  # type: ignore[attr-defined]
    fake_config.RETRY_BACKOFF_SECONDS = 10  # type: ignore[attr-defined]
    fake_config.RETRY_BACKOFF_MULTIPLIER = 2  # type: ignore[attr-defined]
    fake_config.RETRY_JOB_TTL_SECONDS = 86400  # type: ignore[attr-defined]
    fake_config.path_config = MagicMock(root=Path("/app"))  # type: ignore[attr-defined]
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

    sys.modules["src.ingestion.embed"].load_embedder = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    sys.modules["src.ingestion.embed"].get_vector_dim = MagicMock(return_value=384)  # type: ignore[attr-defined]
    sys.modules["src.ingestion.embed"].embed_text = MagicMock()  # type: ignore[attr-defined]

    sys.modules["src.retrieval.vector_store"].init_db = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].search_similar_chunks = MagicMock(return_value=[])  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].get_source_path_for_doc = MagicMock(return_value=None)  # type: ignore[attr-defined]

    sys.modules["src.generation.client"].generate_answer = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].warmup_model = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].ModelGenerationError = _ModelGenerationError  # type: ignore[attr-defined]

    sys.modules["src.generation.prompts"].ACTIVE_PROMPT = "test"  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].build_grounded_prompt = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].build_revision_prompt = MagicMock()  # type: ignore[attr-defined]

    sys.modules["src.generation.router"].select_generation_provider = MagicMock(  # type: ignore[attr-defined]
        return_value=MagicMock(provider="local", score=0.1, threshold=0.65, reasons=())
    )

    sys.modules["src.retry_queue"].RetryJobStatus = _FakeRetryJobStatus  # type: ignore[attr-defined]
    sys.modules["src.retry_queue"].create_retry_job = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.retry_queue"].get_retry_job = MagicMock()  # type: ignore[attr-defined]

    sys.modules["src.ingestion.pipeline"].PipelineError = _PipelineError  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].load_sources = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].run_ingestion = MagicMock()  # type: ignore[attr-defined]


@pytest.fixture(scope="module")
def main_module():
    originals = {name: sys.modules.get(name) for name in _STUBBED_MODULE_NAMES}
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


def _patch_ingest(main_module, monkeypatch, report=None, sources=None, side_effect=None):
    monkeypatch.setattr(
        main_module,
        "load_sources",
        lambda path: sources if sources is not None else FAKE_SOURCES,
    )
    if side_effect:
        monkeypatch.setattr(main_module, "run_ingestion", MagicMock(side_effect=side_effect))
    else:
        monkeypatch.setattr(
            main_module,
            "run_ingestion",
            MagicMock(return_value=report if report is not None else FAKE_REPORT),
        )


class TestIngestValidation:
    def test_non_pdf_rejected(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch)
        resp = client.post(
            "/ingest",
            files={"file": ("notes.txt", b"text content", "text/plain")},
            data={"source_name": "NICE"},
        )
        assert resp.status_code == 422
        assert "pdf" in resp.json()["detail"].lower()

    def test_unknown_source_rejected(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch)
        resp = client.post(
            "/ingest",
            files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
            data={"source_name": "UNKNOWN"},
        )
        assert resp.status_code == 422
        assert "UNKNOWN" in resp.json()["detail"]

    def test_all_known_sources_pass_validation(self, client, main_module, monkeypatch):
        for source in ("NICE", "BSR", "NICE_NEURO"):
            _patch_ingest(main_module, monkeypatch)
            with patch.object(Path, "mkdir"), patch.object(Path, "open", mock_open()), patch("shutil.copyfileobj"):
                resp = client.post(
                    "/ingest",
                    files={"file": ("test.pdf", PDF_BYTES, "application/pdf")},
                    data={"source_name": source},
                )
            assert resp.status_code != 422, f"Source {source} was incorrectly rejected"


class TestIngestSuccess:
    def test_returns_ingestion_report(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch)
        with patch.object(Path, "mkdir"), patch.object(Path, "open", mock_open()), patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["source_name"] == "NICE"
        assert body["filename"] == "NG193.pdf"
        assert body["total_chunks"] == 45
        assert body["embeddings_succeeded"] == 45
        assert body["db"]["inserted"] == 45
        assert body["db"]["failed"] == 0

    def test_run_ingestion_called_with_correct_source(self, client, main_module, monkeypatch):
        mock_run = MagicMock(return_value=FAKE_REPORT)
        monkeypatch.setattr(main_module, "load_sources", lambda path: FAKE_SOURCES)
        monkeypatch.setattr(main_module, "run_ingestion", mock_run)

        with patch.object(Path, "mkdir"), patch.object(Path, "open", mock_open()), patch("shutil.copyfileobj"):
            client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "BSR"},
            )

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["source_name"] == "BSR"
        assert call_kwargs["input_path"].name == "NG193.pdf"

    def test_report_fields_all_present(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch)
        with patch.object(Path, "mkdir"), patch.object(Path, "open", mock_open()), patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        body = resp.json()
        for field in (
            "source_name",
            "filename",
            "files_scanned",
            "files_succeeded",
            "files_failed",
            "total_chunks",
            "embeddings_succeeded",
            "embeddings_failed",
            "db",
        ):
            assert field in body, f"Missing field: {field}"
        for db_key in ("inserted", "updated", "skipped", "failed"):
            assert db_key in body["db"], f"Missing db key: {db_key}"


class TestIngestErrors:
    def test_pipeline_error_returns_500(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch, side_effect=_PipelineError(stage="embed", message="OOM"))
        with patch.object(Path, "mkdir"), patch.object(Path, "open", mock_open()), patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 500
        assert "embed" in resp.json()["detail"]

    def test_value_error_returns_422(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch, side_effect=ValueError("No text extracted"))
        with patch.object(Path, "mkdir"), patch.object(Path, "open", mock_open()), patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("empty.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 422
        assert "No text extracted" in resp.json()["detail"]

    def test_file_save_error_returns_500(self, client, main_module, monkeypatch):
        _patch_ingest(main_module, monkeypatch)
        with patch.object(Path, "mkdir"):
            with patch.object(Path, "open", side_effect=OSError("disk full")):
                resp = client.post(
                    "/ingest",
                    files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                    data={"source_name": "NICE"},
                )

        assert resp.status_code == 500
        assert "disk full" in resp.json()["detail"]

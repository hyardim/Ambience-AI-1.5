"""
Tests for POST /ingest on the RAG service (src/main.py).

Heavy dependencies (pydantic_settings, sentence_transformers, torch, pgvector,
psycopg2, ollama client, etc.) are stubbed inside a module-scoped fixture so
they are torn down after this module finishes and do not pollute other tests.
"""

import importlib
import os
import sys
import types
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, mock_open, patch

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# PipelineError - defined at module level so tests can reference it without
# importing anything from src.*
# ---------------------------------------------------------------------------


class _PipelineError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}: {message}")


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_stub(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


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


@pytest.fixture(scope="module")
def main_app():
    """Stub heavy deps, import the clinical app, then restore sys.modules."""
    _STUBBED = [
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
    saved = {k: sys.modules.pop(k) for k in _STUBBED if k in sys.modules}

    # pydantic_settings
    ps = _make_stub("pydantic_settings")
    ps.BaseSettings = object
    ps.SettingsConfigDict = lambda **kw: None  # type: ignore[assignment]

    # sentence_transformers
    st = _make_stub("sentence_transformers")
    st.SentenceTransformer = MagicMock  # type: ignore[assignment]

    # torch
    _make_stub("torch")

    # pgvector
    _make_stub("pgvector")
    _make_stub("pgvector.sqlalchemy")
    _make_stub("pgvector.psycopg2")

    # psycopg2
    _make_stub("psycopg2")
    _make_stub("psycopg2.extras")
    _make_stub("psycopg2.errors")

    # sqlalchemy
    _make_stub("sqlalchemy")
    _make_stub("sqlalchemy.orm")
    _make_stub("sqlalchemy.pool")
    _make_stub("sqlalchemy.dialects")
    _make_stub("sqlalchemy.dialects.postgresql")
    _make_stub("sqlalchemy.engine")

    # tqdm
    tqdm_mod = _make_stub("tqdm")
    tqdm_mod.tqdm = lambda it, **kw: it  # type: ignore[assignment]

    # nltk
    _make_stub("nltk")
    nltk_tok = _make_stub("nltk.tokenize")
    nltk_tok.sent_tokenize = lambda text, **kw: text.split(". ")  # type: ignore[assignment]

    # fitz (PyMuPDF)
    _make_stub("fitz")
    ask_routes = _make_stub("src.api.ask_routes")
    ask_routes.router = APIRouter()  # type: ignore[attr-defined]

    # src.config - fake module with all symbols that src.main and its imports need
    fake_config = types.ModuleType("src.config")
    fake_config.db_config = types.SimpleNamespace(
        database_url=os.getenv("DATABASE_URL", "postgresql://admin:pw@localhost/test")
    )  # type: ignore[attr-defined]
    fake_config.local_llm_config = types.SimpleNamespace(
        base_url="http://localhost:11434",
        model="fake-local-model",
        api_key="ollama",
        max_tokens=512,
        timeout_seconds=60.0,
    )  # type: ignore[attr-defined]
    fake_config.cloud_llm_config = types.SimpleNamespace(
        base_url="https://example.invalid/v1",
        model="fake-cloud-model",
        api_key="",
        max_tokens=512,
        temperature=0.1,
        timeout_seconds=120.0,
    )  # type: ignore[attr-defined]
    fake_config.routing_config = types.SimpleNamespace(
        llm_route_threshold=0.65,
        force_cloud_llm=False,
        route_revisions_to_cloud=True,
        medium_prompt_chars=3500,
        long_prompt_chars=7000,
    )  # type: ignore[attr-defined]
    fake_config.retry_config = types.SimpleNamespace(
        redis_url="redis://localhost:6379/0",
        retry_enabled=True,
        retry_max_attempts=3,
        retry_backoff_seconds=10,
        retry_backoff_multiplier=2,
        retry_job_ttl_seconds=86400,
    )  # type: ignore[attr-defined]
    fake_config.logging_config = types.SimpleNamespace(
        log_level="INFO",
        log_file="logs/test.log",
    )  # type: ignore[attr-defined]
    fake_config.llm_config = types.SimpleNamespace(
        llm_base_url="http://localhost:11434/v1",
        llm_model="fake-model",
        llm_api_key="ollama",
        llm_max_tokens=512,
        llm_temperature=0.1,
        llm_timeout_seconds=120.0,
    )  # type: ignore[attr-defined]
    fake_config.generation_config = types.SimpleNamespace(
        ollama_base_url="http://localhost:11434",
        ollama_model="fake-local-model",
        ollama_max_tokens=512,
        ollama_timeout_seconds=60.0,
        prompt_variant="test",
    )  # type: ignore[attr-defined]
    _path_config = MagicMock()
    _path_config.root = Path("/app")
    fake_config.path_config = _path_config  # type: ignore[attr-defined]
    sys.modules["src.config"] = fake_config

    # src sub-modules that do heavy I/O at import time
    for _mod_name in (
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
        _make_stub(_mod_name)

    sys.modules["src.ingestion.embed"].load_embedder = MagicMock(
        return_value=MagicMock()
    )  # type: ignore[attr-defined]
    sys.modules["src.ingestion.embed"].get_vector_dim = MagicMock(return_value=384)  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].init_db = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].get_source_path_for_doc = MagicMock(
        return_value=None
    )  # type: ignore[attr-defined]

    class _ModelGenerationError(RuntimeError):
        def __init__(self, message: str, retryable: bool = False) -> None:
            super().__init__(message)
            self.retryable = retryable

    sys.modules["src.generation.client"].ModelGenerationError = _ModelGenerationError  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].ProviderName = Literal["local", "cloud"]  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].generate_answer = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].warmup_model = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.client"]._auth_headers = MagicMock(return_value={})  # type: ignore[attr-defined]
    sys.modules["src.generation.client"]._extract_chat_completion_text = MagicMock(
        return_value="answer"
    )  # type: ignore[attr-defined]
    sys.modules["src.generation.streaming"].stream_generate = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].ACTIVE_PROMPT = "test"  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].build_grounded_prompt = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].build_revision_prompt = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].select_answer_mode = MagicMock(  # type: ignore[attr-defined]
        return_value="strict_guideline"
    )
    sys.modules["src.generation.prompts"].allows_uncited_answer = MagicMock(  # type: ignore[attr-defined]
        return_value=False
    )
    sys.modules["src.ingestion.pipeline"].PipelineError = _PipelineError  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].load_sources = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].run_ingestion = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.jobs.retry"].RetryJobStatus = Literal["queued"]  # type: ignore[attr-defined]
    sys.modules["src.jobs.retry"].create_retry_job = MagicMock(
        return_value=("job-1", "queued")
    )  # type: ignore[attr-defined]
    sys.modules["src.jobs.retry"].get_retry_job = MagicMock(return_value=None)  # type: ignore[attr-defined]

    class _GenerationError(RuntimeError):
        pass

    sys.modules["src.orchestration.generate"].GenerationError = _GenerationError  # type: ignore[attr-defined]
    sys.modules["src.orchestration.generate"].RAGResponse = type("RAGResponse", (), {})  # type: ignore[attr-defined]
    sys.modules["src.orchestration.pipeline"].ask = MagicMock()  # type: ignore[attr-defined]

    class _RetrievalError(RuntimeError):
        pass

    sys.modules["src.retrieval.query"].RetrievalError = _RetrievalError  # type: ignore[attr-defined]

    sys.modules["src.api.services"].retrieve_chunks = MagicMock(return_value=[])  # type: ignore[attr-defined]
    sys.modules["src.api.services"].filter_chunks = MagicMock(
        side_effect=lambda _query, retrieved: retrieved
    )  # type: ignore[attr-defined]
    sys.modules["src.api.services"].NO_EVIDENCE_RESPONSE = "No evidence"  # type: ignore[attr-defined]
    sys.modules["src.api.services"].evidence_level = MagicMock(return_value="strong")  # type: ignore[attr-defined]
    sys.modules["src.api.services"].low_evidence_note = MagicMock(return_value=None)  # type: ignore[attr-defined]
    sys.modules["src.api.services"].log_route_decision = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.api.services"].to_search_result = MagicMock(
        side_effect=_fake_to_search_result
    )  # type: ignore[attr-defined]

    # src.generation.router only uses stdlib + the fake config above.

    try:
        import src.main as _main

        _routes = importlib.import_module("src.api.routes")

        yield types.SimpleNamespace(app=_main.app, routes=_routes)
    finally:
        # Teardown: remove stubs and restore anything that was previously cached
        for k in _STUBBED:
            sys.modules.pop(k, None)
        sys.modules.update(saved)


@pytest.fixture
def client(main_app):
    return TestClient(main_app.app, raise_server_exceptions=False)


def _patch_ingest(monkeypatch, main_app, report=None, sources=None, side_effect=None):
    monkeypatch.setattr(
        main_app.routes,
        "load_sources",
        lambda path: sources if sources is not None else FAKE_SOURCES,
    )
    if side_effect:
        monkeypatch.setattr(
            main_app.routes, "run_ingestion", MagicMock(side_effect=side_effect)
        )
    else:
        monkeypatch.setattr(
            main_app.routes,
            "run_ingestion",
            MagicMock(return_value=report if report is not None else FAKE_REPORT),
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestIngestValidation:
    def test_non_pdf_rejected(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app)
        resp = client.post(
            "/ingest",
            files={"file": ("notes.txt", b"text content", "text/plain")},
            data={"source_name": "NICE"},
        )
        assert resp.status_code == 422
        assert "pdf" in resp.json()["detail"].lower()

    def test_unknown_source_rejected(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app)
        resp = client.post(
            "/ingest",
            files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
            data={"source_name": "UNKNOWN"},
        )
        assert resp.status_code == 422
        assert "UNKNOWN" in resp.json()["detail"]

    def test_all_known_sources_pass_validation(self, client, main_app, monkeypatch):
        for source in ("NICE", "BSR", "NICE_NEURO"):
            _patch_ingest(monkeypatch, main_app)
            with (
                patch.object(Path, "mkdir"),
                patch.object(Path, "open", mock_open()),
                patch("shutil.copyfileobj"),
            ):
                resp = client.post(
                    "/ingest",
                    files={"file": ("test.pdf", PDF_BYTES, "application/pdf")},
                    data={"source_name": source},
                )
            assert resp.status_code != 422, f"Source {source} was incorrectly rejected"


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestIngestSuccess:
    def test_returns_ingestion_report(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app)
        with (
            patch.object(Path, "mkdir"),
            patch.object(Path, "open", mock_open()),
            patch("shutil.copyfileobj"),
        ):
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

    def test_run_ingestion_called_with_correct_source(
        self, client, main_app, monkeypatch
    ):
        mock_run = MagicMock(return_value=FAKE_REPORT)
        monkeypatch.setattr(main_app.routes, "load_sources", lambda path: FAKE_SOURCES)
        monkeypatch.setattr(main_app.routes, "run_ingestion", mock_run)

        with (
            patch.object(Path, "mkdir"),
            patch.object(Path, "open", mock_open()),
            patch("shutil.copyfileobj"),
        ):
            client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "BSR"},
            )

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["source_name"] == "BSR"
        assert call_kwargs["input_path"].name == "NG193.pdf"

    def test_report_fields_all_present(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app)
        with (
            patch.object(Path, "mkdir"),
            patch.object(Path, "open", mock_open()),
            patch("shutil.copyfileobj"),
        ):
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


# ---------------------------------------------------------------------------
# Pipeline error handling
# ---------------------------------------------------------------------------


class TestIngestErrors:
    def test_pipeline_error_returns_500(self, client, main_app, monkeypatch):
        _patch_ingest(
            monkeypatch,
            main_app,
            side_effect=_PipelineError(stage="embed", message="OOM"),
        )
        with (
            patch.object(Path, "mkdir"),
            patch.object(Path, "open", mock_open()),
            patch("shutil.copyfileobj"),
        ):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 500
        assert "embed" in resp.json()["detail"]

    def test_value_error_returns_422(self, client, main_app, monkeypatch):
        _patch_ingest(
            monkeypatch, main_app, side_effect=ValueError("No text extracted")
        )
        with (
            patch.object(Path, "mkdir"),
            patch.object(Path, "open", mock_open()),
            patch("shutil.copyfileobj"),
        ):
            resp = client.post(
                "/ingest",
                files={"file": ("empty.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 422
        assert "No text extracted" in resp.json()["detail"]

    def test_file_save_error_returns_500(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app)
        with (
            patch.object(Path, "mkdir"),
            patch.object(Path, "open", side_effect=OSError("disk full")),
        ):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 500
        assert "disk full" in resp.json()["detail"]

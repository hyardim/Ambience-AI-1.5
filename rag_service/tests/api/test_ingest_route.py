"""
Tests for POST /ingest on the RAG service (src/main.py).

Heavy dependencies (pydantic_settings, sentence_transformers, torch, pgvector,
psycopg2, ollama client, etc.) are stubbed inside a module-scoped fixture so
they are torn down after this module finishes and do not pollute other tests.
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
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


@pytest.fixture(scope="module")
def main_app():
    """Stub heavy/unavailable deps, import src.main, then restore sys.modules."""
    _STUBBED = [
        "pydantic_settings",
        "sentence_transformers",
        "torch",
        "pgvector", "pgvector.sqlalchemy", "pgvector.psycopg2",
        "psycopg2", "psycopg2.extras", "psycopg2.errors",
        "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.pool",
        "sqlalchemy.dialects", "sqlalchemy.dialects.postgresql", "sqlalchemy.engine",
        "tqdm",
        "nltk", "nltk.tokenize",
        "fitz",
        "src.config",
        "src.ingestion.embed",
        "src.ingestion.pipeline",
        "src.retrieval.vector_store",
        "src.generation.client",
        "src.generation.prompts",
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

    # src.config - fake module with all symbols that src.main and its imports need
    fake_config = types.ModuleType("src.config")
    fake_config.DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:pw@localhost/test")  # type: ignore[attr-defined]
    fake_config.OLLAMA_MODEL = "fake-model"  # type: ignore[attr-defined]
    fake_config.OLLAMA_MAX_TOKENS = 512  # type: ignore[attr-defined]
    fake_config.CLOUD_LLM_MODEL = "fake-cloud-model"  # type: ignore[attr-defined]
    fake_config.FORCE_CLOUD_LLM = False  # type: ignore[attr-defined]
    fake_config.LLM_MAX_TOKENS = 512  # type: ignore[attr-defined]
    fake_config.LLM_ROUTE_THRESHOLD = 0.65  # type: ignore[attr-defined]
    fake_config.LOCAL_LLM_MODEL = "fake-local-model"  # type: ignore[attr-defined]
    fake_config.ROUTE_REVISIONS_TO_CLOUD = True  # type: ignore[attr-defined]
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
        "src.generation.prompts",
    ):
        _make_stub(_mod_name)

    sys.modules["src.ingestion.embed"].load_embedder = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    sys.modules["src.ingestion.embed"].get_vector_dim = MagicMock(return_value=384)  # type: ignore[attr-defined]
    sys.modules["src.ingestion.embed"].embed_text = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].init_db = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].search_similar_chunks = MagicMock(return_value=[])  # type: ignore[attr-defined]
    sys.modules["src.retrieval.vector_store"].get_source_path_for_doc = MagicMock(return_value=None)  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].generate_answer = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.client"].warmup_model = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].ACTIVE_PROMPT = "test"  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].build_grounded_prompt = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.generation.prompts"].build_revision_prompt = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].PipelineError = _PipelineError  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].load_sources = MagicMock()  # type: ignore[attr-defined]
    sys.modules["src.ingestion.pipeline"].run_ingestion = MagicMock()  # type: ignore[attr-defined]

    # src.generation.router only uses stdlib + src.config so let it load for real
    # (fake_config already has FORCE_CLOUD_LLM, LLM_ROUTE_THRESHOLD, ROUTE_REVISIONS_TO_CLOUD)

    import src.main as _main  # noqa: E402

    yield _main

    # Teardown: remove stubs and restore anything that was previously cached
    for k in _STUBBED:
        sys.modules.pop(k, None)
    sys.modules.update(saved)


@pytest.fixture()
def client(main_app):
    return TestClient(main_app.app, raise_server_exceptions=False)


def _patch_ingest(monkeypatch, main_app, report=None, sources=None, side_effect=None):
    monkeypatch.setattr(
        main_app, "load_sources",
        lambda path: sources if sources is not None else FAKE_SOURCES,
    )
    if side_effect:
        monkeypatch.setattr(main_app, "run_ingestion", MagicMock(side_effect=side_effect))
    else:
        monkeypatch.setattr(
            main_app, "run_ingestion",
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
            with patch.object(Path, "mkdir"), \
                 patch.object(Path, "open", mock_open()), \
                 patch("shutil.copyfileobj"):
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
        with patch.object(Path, "mkdir"), \
             patch.object(Path, "open", mock_open()), \
             patch("shutil.copyfileobj"):
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

    def test_run_ingestion_called_with_correct_source(self, client, main_app, monkeypatch):
        mock_run = MagicMock(return_value=FAKE_REPORT)
        monkeypatch.setattr(main_app, "load_sources", lambda path: FAKE_SOURCES)
        monkeypatch.setattr(main_app, "run_ingestion", mock_run)

        with patch.object(Path, "mkdir"), \
             patch.object(Path, "open", mock_open()), \
             patch("shutil.copyfileobj"):
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
        with patch.object(Path, "mkdir"), \
             patch.object(Path, "open", mock_open()), \
             patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        body = resp.json()
        for field in ("source_name", "filename", "files_scanned", "files_succeeded",
                      "files_failed", "total_chunks", "embeddings_succeeded",
                      "embeddings_failed", "db"):
            assert field in body, f"Missing field: {field}"
        for db_key in ("inserted", "updated", "skipped", "failed"):
            assert db_key in body["db"], f"Missing db key: {db_key}"


# ---------------------------------------------------------------------------
# Pipeline error handling
# ---------------------------------------------------------------------------

class TestIngestErrors:

    def test_pipeline_error_returns_500(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app, side_effect=_PipelineError(stage="embed", message="OOM"))
        with patch.object(Path, "mkdir"), \
             patch.object(Path, "open", mock_open()), \
             patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 500
        assert "embed" in resp.json()["detail"]

    def test_value_error_returns_422(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app, side_effect=ValueError("No text extracted"))
        with patch.object(Path, "mkdir"), \
             patch.object(Path, "open", mock_open()), \
             patch("shutil.copyfileobj"):
            resp = client.post(
                "/ingest",
                files={"file": ("empty.pdf", PDF_BYTES, "application/pdf")},
                data={"source_name": "NICE"},
            )

        assert resp.status_code == 422
        assert "No text extracted" in resp.json()["detail"]

    def test_file_save_error_returns_500(self, client, main_app, monkeypatch):
        _patch_ingest(monkeypatch, main_app)
        with patch.object(Path, "mkdir"):
            with patch.object(Path, "open", side_effect=OSError("disk full")):
                resp = client.post(
                    "/ingest",
                    files={"file": ("NG193.pdf", PDF_BYTES, "application/pdf")},
                    data={"source_name": "NICE"},
                )

        assert resp.status_code == 500
        assert "disk full" in resp.json()["detail"]

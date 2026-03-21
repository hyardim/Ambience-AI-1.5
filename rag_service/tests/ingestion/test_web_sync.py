from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

import src.ingestion.web_sync as web_sync
from src.ingestion.web_sources import DiscoveredDocument
from src.ingestion.web_sync import (
    GuidelineWebSync,
    SyncAlreadyRunningError,
    _compute_file_hash,
    _download_file,
    _run_ingestion,
)


class _FakeDiscoveryClient:
    def __init__(self, docs: list[DiscoveredDocument]) -> None:
        self._docs = docs

    async def discover_source(self, source) -> list[DiscoveredDocument]:
        return [doc for doc in self._docs if doc.source_name == source.source_name]


def _make_doc(
    *,
    canonical_url: str,
    doc_url: str,
    source_name: str = "NICE",
    specialty: str = "rheumatology",
    title: str = "Rheumatoid arthritis guideline",
    etag: str | None = "etag-v1",
) -> DiscoveredDocument:
    return DiscoveredDocument(
        canonical_url=canonical_url,
        title=title,
        source_name=source_name,
        specialty=specialty,
        doc_url=doc_url,
        publisher="NICE",
        etag=etag,
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        content_length=100,
        discovered_at="2026-01-01T00:00:00+00:00",
    )


def test_sync_downloads_missing_document_and_ingests(
    monkeypatch, tmp_path: Path
) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )

    async def fake_download(**kwargs):
        destination = kwargs["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-pdf")
        return (
            hashlib.sha256(b"fake-pdf").hexdigest(),
            {"etag": "etag-v1", "last_modified": "Wed", "content_length": "8"},
        )

    monkeypatch.setattr("src.ingestion.web_sync._download_file", fake_download)
    monkeypatch.setattr("src.ingestion.web_sync._run_ingestion", lambda **kwargs: {})

    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    summary = result["summary"]
    assert summary["downloaded_new_count"] == 1
    assert summary["ingest_succeeded_count"] == 1
    assert summary["errors"] == []


def test_sync_skips_unchanged_document(monkeypatch, tmp_path: Path) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
        etag="etag-same",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )
    sync.save_state(
        {
            "version": 1,
            "documents": {
                "NICE|https://www.nice.org.uk/guidance/ng193": {
                    "source_name": "NICE",
                    "etag": "etag-same",
                    "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                    "content_length": 100,
                    "content_hash": "abc",
                    "local_path": str(tmp_path / "existing.pdf"),
                }
            },
            "last_run": None,
        }
    )

    calls = {"download": 0}

    async def fake_download(**kwargs):
        calls["download"] += 1
        return (
            "unused",
            {"etag": "etag-same", "last_modified": "Wed", "content_length": "100"},
        )

    monkeypatch.setattr("src.ingestion.web_sync._download_file", fake_download)

    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    summary = result["summary"]
    assert summary["skipped_unchanged_count"] == 1
    assert calls["download"] == 0


def test_sync_downloads_updated_document(monkeypatch, tmp_path: Path) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
        etag="etag-new",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )
    sync.save_state(
        {
            "version": 1,
            "documents": {
                "NICE|https://www.nice.org.uk/guidance/ng193": {
                    "source_name": "NICE",
                    "etag": "etag-old",
                    "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                    "content_length": 100,
                    "content_hash": "oldhash",
                    "local_path": str(tmp_path / "existing.pdf"),
                }
            },
            "last_run": None,
        }
    )

    async def fake_download(**kwargs):
        destination = kwargs["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"updated-pdf")
        return (
            hashlib.sha256(b"updated-pdf").hexdigest(),
            {"etag": "etag-new", "last_modified": "Thu", "content_length": "11"},
        )

    monkeypatch.setattr("src.ingestion.web_sync._download_file", fake_download)
    monkeypatch.setattr("src.ingestion.web_sync._run_ingestion", lambda **kwargs: {})

    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    summary = result["summary"]
    assert summary["downloaded_updated_count"] == 1
    assert summary["ingest_succeeded_count"] == 1


def test_download_file_uses_response_headers_and_writes_content(tmp_path: Path) -> None:
    content = b"%PDF-1.4 mocked"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "ETag": "etag-123",
                "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                "Content-Length": str(len(content)),
            },
            content=content,
        )

    transport = httpx.MockTransport(handler)
    destination = tmp_path / "doc.pdf"

    async def run() -> tuple[str, dict[str, str | None]]:
        async with httpx.AsyncClient(transport=transport) as client:
            return await _download_file(
                client=client,
                url="https://example.com/doc.pdf",
                destination=destination,
                timeout_seconds=5,
                user_agent="test-agent",
            )

    content_hash, metadata = asyncio.run(run())
    assert destination.read_bytes() == content
    assert content_hash == hashlib.sha256(content).hexdigest()
    assert metadata["etag"] == "etag-123"
    assert metadata["content_length"] == str(len(content))


def test_default_state_path_falls_back_to_root(monkeypatch, tmp_path: Path) -> None:
    class _PathConfig:
        root = tmp_path

    monkeypatch.setattr(web_sync, "path_config", _PathConfig())
    assert web_sync._default_state_path() == (
        tmp_path / "data" / "raw" / "_sync_state" / "guideline_sync_state.json"
    )


def test_compute_file_hash(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"abc123")
    assert _compute_file_hash(path) == hashlib.sha256(b"abc123").hexdigest()


def test_load_state_handles_non_dict_content(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    sync = GuidelineWebSync(state_path=state_path)
    assert sync.load_state() == {"version": 1, "documents": {}, "last_run": None}


def test_last_status_exposes_last_run(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    sync = GuidelineWebSync(state_path=state_path)
    sync.save_state(
        {
            "version": 1,
            "documents": {},
            "last_run": {"summary": {"discovered_count": 0}},
        }
    )
    status = sync.last_status()
    assert status["running"] is False
    assert status["last_run"] is not None


def test_sync_once_raises_when_already_running(tmp_path: Path) -> None:
    sync = GuidelineWebSync(state_path=tmp_path / "state.json")

    async def run_locked() -> None:
        async with sync._lock:
            with pytest.raises(SyncAlreadyRunningError):
                await sync.sync_once(db_url="postgresql://localhost/test")

    asyncio.run(run_locked())


def test_sync_once_records_discovery_error(monkeypatch, tmp_path: Path) -> None:
    class _FailDiscovery:
        async def discover_source(self, source):
            del source
            raise RuntimeError("discovery broke")

    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FailDiscovery(),
    )

    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    errors = result["summary"]["errors"]
    assert errors
    assert "discovery failed" in errors[0]


def test_sync_once_dry_run_counts_downloads(monkeypatch, tmp_path: Path) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )

    result = asyncio.run(
        sync.sync_once(db_url="postgresql://localhost/test", dry_run=True)
    )
    assert result["summary"]["downloaded_new_count"] == 1


def test_sync_once_records_download_failure(monkeypatch, tmp_path: Path) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )

    async def fail_download(**kwargs):
        del kwargs
        raise RuntimeError("download boom")

    monkeypatch.setattr("src.ingestion.web_sync._download_file", fail_download)
    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    assert any("download failed" in err for err in result["summary"]["errors"])


def test_sync_once_skips_when_content_hash_unchanged(
    monkeypatch, tmp_path: Path
) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
        etag="etag-new",
    )
    existing_path = tmp_path / "existing.pdf"
    existing_path.write_bytes(b"same-content")
    content_hash = hashlib.sha256(b"same-content").hexdigest()

    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )
    sync.save_state(
        {
            "version": 1,
            "documents": {
                "NICE|https://www.nice.org.uk/guidance/ng193": {
                    "source_name": "NICE",
                    "etag": "etag-old",
                    "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                    "content_length": 100,
                    "content_hash": content_hash,
                    "local_path": str(existing_path),
                }
            },
            "last_run": None,
        }
    )

    async def fake_download(**kwargs):
        destination = kwargs["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"same-content")
        return (
            content_hash,
            {"etag": "etag-new", "last_modified": "Thu", "content_length": "12"},
        )

    monkeypatch.setattr("src.ingestion.web_sync._download_file", fake_download)
    monkeypatch.setattr("src.ingestion.web_sync._run_ingestion", lambda **kwargs: {})
    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    assert result["summary"]["skipped_unchanged_count"] == 1


def test_sync_once_records_ingestion_failure_and_stale_docs(
    monkeypatch, tmp_path: Path
) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )
    sync.save_state(
        {
            "version": 1,
            "documents": {
                "NICE|https://www.nice.org.uk/guidance/stale": {
                    "source_name": "NICE",
                    "title": "Old",
                }
            },
            "last_run": None,
        }
    )

    async def fake_download(**kwargs):
        destination = kwargs["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"new-content")
        return (
            hashlib.sha256(b"new-content").hexdigest(),
            {"etag": "etag-v1", "last_modified": "Wed", "content_length": "11"},
        )

    monkeypatch.setattr("src.ingestion.web_sync._download_file", fake_download)

    def fail_ingest(**kwargs):
        del kwargs
        raise RuntimeError("ingest failed")

    monkeypatch.setattr("src.ingestion.web_sync._run_ingestion", fail_ingest)
    result = asyncio.run(sync.sync_once(db_url="postgresql://localhost/test"))
    assert result["summary"]["ingest_failed_count"] == 1
    assert any("ingestion failed" in err for err in result["summary"]["errors"])

    state = sync.load_state()
    stale = state["documents"]["NICE|https://www.nice.org.uk/guidance/stale"]
    assert stale["stale"] is True


def test_run_ingestion_wrapper_calls_pipeline(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_ingestion(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    import src.ingestion.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "run_ingestion", fake_run_ingestion)
    result = _run_ingestion(input_path=Path("/tmp/x"), source_name="NICE", db_url="d")
    assert result == {"ok": True}
    assert captured["source_name"] == "NICE"


def test_sync_once_dry_run_counts_updated_documents(tmp_path: Path) -> None:
    doc = _make_doc(
        canonical_url="https://www.nice.org.uk/guidance/ng193",
        doc_url="https://cdn.example.com/ng193.pdf",
        etag="etag-new",
    )
    sync = GuidelineWebSync(
        state_path=tmp_path / "state.json",
        discovery_client=_FakeDiscoveryClient([doc]),
    )
    sync.save_state(
        {
            "version": 1,
            "documents": {
                "NICE|https://www.nice.org.uk/guidance/ng193": {
                    "source_name": "NICE",
                    "etag": "etag-old",
                    "last_modified": "Wed, 01 Jan 2025 00:00:00 GMT",
                    "content_length": 100,
                }
            },
            "last_run": None,
        }
    )

    result = asyncio.run(
        sync.sync_once(db_url="postgresql://localhost/test", dry_run=True)
    )
    assert result["summary"]["downloaded_updated_count"] == 1

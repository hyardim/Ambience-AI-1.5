from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx

from src.ingestion.web_sources import DiscoveredDocument
from src.ingestion.web_sync import GuidelineWebSync, _download_file


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

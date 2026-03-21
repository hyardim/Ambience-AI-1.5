from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import path_config
from ..utils.logger import setup_logger
from .web_sources import DEFAULT_USER_AGENT, DiscoveredDocument, SourceDiscoveryClient, WEB_SOURCES

logger = setup_logger(__name__)


def _default_state_path() -> Path:
    data_raw = getattr(path_config, "data_raw", None)
    if isinstance(data_raw, Path):
        return data_raw / "_sync_state" / "guideline_sync_state.json"
    root = getattr(path_config, "root", Path.cwd())
    return Path(root) / "data" / "raw" / "_sync_state" / "guideline_sync_state.json"


SYNC_STATE_PATH = _default_state_path()


class SyncAlreadyRunningError(RuntimeError):
    pass


@dataclass
class SyncSummary:
    discovered_count: int = 0
    downloaded_new_count: int = 0
    downloaded_updated_count: int = 0
    skipped_unchanged_count: int = 0
    ingest_succeeded_count: int = 0
    ingest_failed_count: int = 0
    errors: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "discovered_count": self.discovered_count,
            "downloaded_new_count": self.downloaded_new_count,
            "downloaded_updated_count": self.downloaded_updated_count,
            "skipped_unchanged_count": self.skipped_unchanged_count,
            "ingest_succeeded_count": self.ingest_succeeded_count,
            "ingest_failed_count": self.ingest_failed_count,
            "errors": self.errors or [],
        }


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return cleaned or "guideline"


def _source_directory(source_name: str, specialty: str) -> Path:
    return path_config.data_raw / specialty / source_name


def _document_key(document: DiscoveredDocument) -> str:
    return f"{document.source_name}|{document.canonical_url}"


def _compute_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 64), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_ingestion(**kwargs: Any) -> dict[str, Any]:
    from .pipeline import run_ingestion

    return run_ingestion(**kwargs)


async def _download_file(
    *,
    client: httpx.AsyncClient,
    url: str,
    destination: Path,
    timeout_seconds: float,
    user_agent: str,
) -> tuple[str, dict[str, str | None]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")

    headers = {"User-Agent": user_agent}
    async with client.stream(
        "GET",
        url,
        headers=headers,
        timeout=timeout_seconds,
        follow_redirects=True,
    ) as response:
        response.raise_for_status()

        digest = hashlib.sha256()
        with temp_path.open("wb") as handle:
            async for data in response.aiter_bytes():
                handle.write(data)
                digest.update(data)

        downloaded_meta = {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "content_length": response.headers.get("Content-Length"),
        }

    temp_path.replace(destination)
    return digest.hexdigest(), downloaded_meta


class GuidelineWebSync:
    def __init__(
        self,
        *,
        state_path: Path = SYNC_STATE_PATH,
        user_agent: str = DEFAULT_USER_AGENT,
        discovery_client: SourceDiscoveryClient | None = None,
    ) -> None:
        self._state_path = state_path
        self._user_agent = user_agent
        self._discovery_client = discovery_client or SourceDiscoveryClient(
            user_agent=user_agent
        )
        self._lock = asyncio.Lock()

    def load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {
                "version": 1,
                "documents": {},
                "last_run": None,
            }
        with self._state_path.open("r", encoding="utf-8") as handle:
            content = json.load(handle)
        if not isinstance(content, dict):
            return {"version": 1, "documents": {}, "last_run": None}
        content.setdefault("version", 1)
        content.setdefault("documents", {})
        content.setdefault("last_run", None)
        return content

    def save_state(self, state: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._state_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        temp_path.replace(self._state_path)

    async def sync_once(
        self,
        *,
        db_url: str,
        source_names: set[str] | None = None,
        dry_run: bool = False,
        timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        if self._lock.locked():
            raise SyncAlreadyRunningError("Guideline sync already running")

        async with self._lock:
            started_at = datetime.now(timezone.utc).isoformat()
            summary = SyncSummary(errors=[])
            state = self.load_state()
            state_documents: dict[str, Any] = state.get("documents", {})
            now = datetime.now(timezone.utc).isoformat()

            allowed_sources = [
                source
                for source in WEB_SOURCES.values()
                if source_names is None or source.source_name in source_names
            ]

            async with httpx.AsyncClient() as client:
                for source in allowed_sources:
                    try:
                        discovered = await self._discovery_client.discover_source(source)
                    except Exception as exc:
                        summary.errors.append(
                            f"discovery failed for {source.source_name}: {exc}"
                        )
                        continue

                    summary.discovered_count += len(discovered)
                    seen_keys: set[str] = set()

                    for document in discovered:
                        key = _document_key(document)
                        seen_keys.add(key)

                        existing = state_documents.get(key, {})
                        filename_base = _sanitize_filename(document.title)
                        suffix = hashlib.sha1(
                            document.canonical_url.encode("utf-8")).hexdigest()[:10]
                        destination_dir = _source_directory(
                            document.source_name,
                            document.specialty,
                        )
                        destination = destination_dir / \
                            f"{filename_base}-{suffix}.pdf"

                        existing_etag = existing.get("etag")
                        if existing_etag and document.etag:
                            header_unchanged = existing_etag == document.etag
                        else:
                            header_unchanged = (
                                bool(existing.get("last_modified"))
                                and existing.get("last_modified")
                                == document.last_modified
                                and existing.get("content_length")
                                == document.content_length
                            )

                        is_missing = not existing
                        needs_download = is_missing or not header_unchanged

                        if not needs_download:
                            summary.skipped_unchanged_count += 1
                            state_documents[key] = {
                                **existing,
                                "last_seen": now,
                                "stale": False,
                                "discovered": {
                                    "title": document.title,
                                    "doc_url": document.doc_url,
                                },
                            }
                            continue

                        if dry_run:
                            if is_missing:
                                summary.downloaded_new_count += 1
                            else:
                                summary.downloaded_updated_count += 1
                            continue

                        try:
                            content_hash, headers = await asyncio.wait_for(
                                _download_file(
                                    client=client,
                                    url=document.doc_url,
                                    destination=destination,
                                    timeout_seconds=timeout_seconds,
                                    user_agent=self._user_agent,
                                ),
                                timeout=timeout_seconds,
                            )
                        except Exception as exc:
                            summary.errors.append(
                                f"download failed for {document.doc_url}: {exc}"
                            )
                            continue

                        previous_hash = existing.get("content_hash")
                        if previous_hash and previous_hash == content_hash and destination.exists():
                            summary.skipped_unchanged_count += 1
                        elif is_missing:
                            summary.downloaded_new_count += 1
                        else:
                            summary.downloaded_updated_count += 1

                        try:
                            _run_ingestion(
                                input_path=destination,
                                source_name=document.source_name,
                                db_url=db_url,
                            )
                            summary.ingest_succeeded_count += 1
                            last_ingest = now
                        except Exception as exc:
                            summary.ingest_failed_count += 1
                            summary.errors.append(
                                f"ingestion failed for {destination.name}: {exc}"
                            )
                            last_ingest = existing.get(
                                "last_successful_ingest")

                        resolved_content_length = headers.get("content_length")
                        parsed_length = (
                            int(resolved_content_length)
                            if resolved_content_length and str(resolved_content_length).isdigit()
                            else document.content_length
                        )

                        state_documents[key] = {
                            "source_name": document.source_name,
                            "specialty": document.specialty,
                            "canonical_url": document.canonical_url,
                            "doc_url": document.doc_url,
                            "title": document.title,
                            "etag": headers.get("etag") or document.etag,
                            "last_modified": headers.get("last_modified")
                            or document.last_modified,
                            "content_length": parsed_length,
                            "content_hash": content_hash,
                            "local_path": str(destination),
                            "last_successful_ingest": last_ingest,
                            "last_seen": now,
                            "stale": False,
                            "discovered_at": document.discovered_at,
                        }

                    for key, doc_state in list(state_documents.items()):
                        if doc_state.get("source_name") != source.source_name:
                            continue
                        if key in seen_keys:
                            continue
                        doc_state["stale"] = True
                        doc_state["stale_since"] = now
                        doc_state["last_seen"] = now

            state["documents"] = state_documents
            state["last_run"] = {
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "summary": summary.as_dict(),
            }
            self.save_state(state)

            logger.info(
                "sync.complete discovered=%s new=%s updated=%s unchanged=%s ingest_ok=%s ingest_failed=%s errors=%s",
                summary.discovered_count,
                summary.downloaded_new_count,
                summary.downloaded_updated_count,
                summary.skipped_unchanged_count,
                summary.ingest_succeeded_count,
                summary.ingest_failed_count,
                len(summary.errors or []),
            )
            return state["last_run"]

    def last_status(self) -> dict[str, Any]:
        state = self.load_state()
        last_run = state.get("last_run")
        return {
            "running": self._lock.locked(),
            "last_run": last_run,
        }

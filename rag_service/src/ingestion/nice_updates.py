from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml

from ..config import path_config
from ..ingestion.metadata import infer_from_path
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class NiceApiSettings:
    api_key: str | None
    base_url: str | None
    guidance_endpoint: str
    timeout_seconds: float
    api_key_header: str
    id_field: str
    updated_field: str
    pdf_url_field: str
    version_field: str
    result_path: str
    id_prefixes: tuple[str, ...]


def load_nice_settings() -> NiceApiSettings:
    prefixes = tuple(
        p.strip().lower()
        for p in os.getenv("NICE_ID_PREFIXES", "NG,CG,QS,TA").split(",")
        if p.strip()
    )
    return NiceApiSettings(
        api_key=os.getenv("NICE_API_KEY"),
        base_url=os.getenv("NICE_API_BASE_URL"),
        guidance_endpoint=os.getenv("NICE_API_GUIDANCE_ENDPOINT", ""),
        timeout_seconds=float(os.getenv("NICE_API_TIMEOUT_SECONDS", "20")),
        api_key_header=os.getenv("NICE_API_KEY_HEADER", "x-api-key"),
        id_field=os.getenv("NICE_API_ID_FIELD", "id"),
        updated_field=os.getenv("NICE_API_UPDATED_FIELD", "lastUpdated"),
        pdf_url_field=os.getenv("NICE_API_PDF_URL_FIELD", "pdfUrl"),
        version_field=os.getenv("NICE_API_VERSION_FIELD", "version"),
        result_path=os.getenv("NICE_API_RESULT_PATH", ""),
        id_prefixes=prefixes,
    )


@dataclass(frozen=True)
class LocalGuideline:
    path: Path
    specialty: str
    source_name: str
    nice_id: str | None
    content_type: str


@dataclass(frozen=True)
class NiceGuideline:
    nice_id: str
    content_type: str
    pdf_url: str
    last_updated: str | None
    version: str | None


def _load_mapping(map_path: Path) -> dict[str, Any]:
    if not map_path.exists():
        return {"mappings": {}, "defaults": {"content_type": "guidance"}}
    with map_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {"mappings": {}, "defaults": {"content_type": "guidance"}}
    data.setdefault("mappings", {})
    data.setdefault("defaults", {"content_type": "guidance"})
    return data


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        with state_path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def _discover_local_pdfs(data_root: Path) -> list[Path]:
    return sorted(data_root.rglob("*.pdf"))


def _infer_nice_id(filename: str, id_prefixes: tuple[str, ...]) -> str | None:
    lowered = filename.lower()
    for prefix in id_prefixes:
        match = re.search(rf"\b{re.escape(prefix)}\d+\b", lowered)
        if match:
            return match.group(0)
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resolve_mapping_entry(
    mappings: dict[str, Any],
    relative_path: str,
    filename: str,
) -> dict[str, Any] | None:
    if relative_path in mappings:
        return mappings[relative_path]
    if filename in mappings:
        return mappings[filename]
    return None


def _should_update(
    remote: NiceGuideline,
    previous: dict[str, Any],
    local_path: Path,
) -> bool:
    remote_updated = _parse_datetime(remote.last_updated)
    previous_updated = _parse_datetime(previous.get("last_updated"))

    if remote_updated and previous_updated:
        return remote_updated > previous_updated

    if remote_updated:
        local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime)
        return remote_updated > local_mtime

    if remote.version and previous.get("version"):
        return remote.version != previous.get("version")

    if remote.pdf_url and previous.get("pdf_url"):
        return remote.pdf_url != previous.get("pdf_url")

    return False


def _extract_result(payload: dict[str, Any], result_path: str) -> dict[str, Any]:
    if not result_path:
        return payload
    current: Any = payload
    for part in result_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return payload
        current = current[part]
    return current if isinstance(current, dict) else payload


class NiceSyndicationClient:
    def __init__(self, settings: NiceApiSettings) -> None:
        self._settings = settings

    def _build_headers(self) -> dict[str, str]:
        if not self._settings.api_key:
            return {}
        return {self._settings.api_key_header: self._settings.api_key}

    def _build_guidance_url(self, content_type: str, nice_id: str) -> str:
        endpoint = self._settings.guidance_endpoint or f"/{content_type}/{nice_id}"
        endpoint = endpoint.format(content_type=content_type, nice_id=nice_id)
        return urljoin(self._settings.base_url or "", endpoint)

    def fetch_guideline(self, nice_id: str, content_type: str) -> NiceGuideline | None:
        url = self._build_guidance_url(content_type, nice_id)
        if not url:
            return None
        try:
            with httpx.Client(timeout=self._settings.timeout_seconds) as client:
                response = client.get(url, headers=self._build_headers())
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning("NICE API request failed for %s: %s", nice_id, exc)
            return None
        except ValueError as exc:
            logger.warning("NICE API returned invalid JSON for %s: %s", nice_id, exc)
            return None

        data = _extract_result(payload, self._settings.result_path)
        pdf_url = data.get(self._settings.pdf_url_field)
        if not pdf_url:
            logger.warning("NICE API response missing pdf url for %s", nice_id)
            return None

        return NiceGuideline(
            nice_id=str(data.get(self._settings.id_field, nice_id)),
            content_type=content_type,
            pdf_url=str(pdf_url),
            last_updated=data.get(self._settings.updated_field),
            version=data.get(self._settings.version_field),
        )

    def download_pdf(self, url: str, destination: Path) -> bool:
        temp_path = destination.with_suffix(destination.suffix + ".download")
        try:
            with httpx.Client(timeout=self._settings.timeout_seconds) as client:
                with client.stream("GET", url, headers=self._build_headers()) as resp:
                    resp.raise_for_status()
                    with temp_path.open("wb") as handle:
                        for chunk in resp.iter_bytes():
                            handle.write(chunk)
        except httpx.HTTPError as exc:
            logger.warning("Failed to download NICE PDF %s: %s", url, exc)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False
        except OSError as exc:
            logger.warning("Failed to write NICE PDF to %s: %s", destination, exc)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False

        try:
            temp_path.replace(destination)
        except OSError as exc:
            logger.warning("Failed to replace %s: %s", destination, exc)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            return False

        return True


def update_nice_guidelines(
    data_root: Path | None = None,
    db_url: str | None = None,
    dry_run: bool = False,
    max_files: int | None = None,
    ingest: bool = True,
) -> dict[str, Any]:
    settings = load_nice_settings()

    if not settings.api_key:
        logger.info("NICE_API_KEY not set; skipping NICE updates.")
        return {"scanned": 0, "matched": 0, "updated": 0, "skipped": 0}

    if not settings.base_url or not settings.guidance_endpoint:
        logger.warning("NICE API base URL or endpoint not configured; skipping.")
        return {"scanned": 0, "matched": 0, "updated": 0, "skipped": 0}

    data_root = data_root or path_config.data_raw
    if not data_root.exists():
        logger.warning("NICE update data root not found: %s", data_root)
        return {"scanned": 0, "matched": 0, "updated": 0, "skipped": 0}
    map_path = path_config.root / "configs" / "nice_guideline_map.yaml"
    state_path = path_config.data_processed / "nice_sync_state.json"

    mapping = _load_mapping(map_path)
    mappings = mapping.get("mappings", {})
    defaults = mapping.get("defaults", {})
    content_default = defaults.get("content_type", "guidance")

    state = _load_state(state_path)
    pdfs = _discover_local_pdfs(data_root)
    if max_files is not None:
        pdfs = pdfs[:max_files]

    summary = {
        "scanned": len(pdfs),
        "matched": 0,
        "updated": 0,
        "skipped": 0,
        "ingested": 0,
        "failed": 0,
    }

    client = NiceSyndicationClient(settings)
    updated_state: dict[str, Any] = dict(state)

    for pdf_path in pdfs:
        relative = str(pdf_path.relative_to(data_root))
        mapping_entry = _resolve_mapping_entry(mappings, relative, pdf_path.name)
        nice_id = None
        content_type = content_default

        if mapping_entry:
            nice_id = mapping_entry.get("nice_id")
            content_type = mapping_entry.get("content_type", content_default)

        if not nice_id:
            nice_id = _infer_nice_id(pdf_path.stem, settings.id_prefixes)

        if not nice_id:
            summary["skipped"] += 1
            continue

        summary["matched"] += 1

        remote = client.fetch_guideline(nice_id, content_type)
        if not remote:
            summary["failed"] += 1
            continue

        previous = state.get(relative, {})
        if not _should_update(remote, previous, pdf_path):
            summary["skipped"] += 1
            continue

        if dry_run:
            logger.info("Update available for %s (dry run)", pdf_path.name)
            summary["updated"] += 1
            continue

        if not client.download_pdf(remote.pdf_url, pdf_path):
            summary["failed"] += 1
            continue

        updated_state[relative] = {
            "nice_id": remote.nice_id,
            "content_type": remote.content_type,
            "pdf_url": remote.pdf_url,
            "last_updated": remote.last_updated,
            "version": remote.version,
            "updated_at": datetime.utcnow().isoformat(),
        }
        summary["updated"] += 1

        if ingest:
            if db_url is None and not dry_run:
                raise ValueError("db_url is required when ingest=True and dry_run=False")

            source_meta = infer_from_path(str(pdf_path))
            source_name = mapping_entry.get("source_name") if mapping_entry else None
            if not source_name:
                source_name = source_meta.get("source_name", "")

            if not source_name:
                logger.warning("Unable to infer source_name for %s", pdf_path)
                summary["failed"] += 1
                continue

            from .pipeline import run_ingestion

            report = run_ingestion(
                input_path=pdf_path,
                source_name=source_name,
                db_url=db_url,
            )
            if report.get("files_failed", 0) == 0:
                summary["ingested"] += 1

    _save_state(state_path, updated_state)
    return summary

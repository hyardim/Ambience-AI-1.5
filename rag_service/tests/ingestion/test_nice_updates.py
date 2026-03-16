from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import src.ingestion.nice_updates as nice_updates
from src.config import path_config
from src.ingestion.nice_updates import NiceGuideline


def _write_mapping(root: Path, entry: dict[str, Any]) -> None:
    config_dir = root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    mapping = {"mappings": {"rheumatology/NICE/NG128.pdf": entry}}
    (config_dir / "nice_guideline_map.yaml").write_text(
        "mappings:\n"
        "  rheumatology/NICE/NG128.pdf:\n"
        f"    nice_id: {entry['nice_id']}\n"
        "    content_type: guidance\n"
        f"    source_name: {entry['source_name']}\n",
        encoding="utf-8",
    )


def test_load_nice_settings_prefixes_lowercase(monkeypatch: Any) -> None:
    monkeypatch.setenv("NICE_ID_PREFIXES", "NG, QS")
    settings = nice_updates.load_nice_settings()
    assert settings.id_prefixes == ("ng", "qs")


def test_update_skips_without_api_key(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("NICE_API_KEY", raising=False)
    summary = nice_updates.update_nice_guidelines(data_root=tmp_path)
    assert summary == {"scanned": 0, "matched": 0, "updated": 0, "skipped": 0}


def test_update_downloads_and_ingests(tmp_path: Path, monkeypatch: Any) -> None:
    data_root = tmp_path / "data" / "raw"
    pdf_dir = data_root / "rheumatology" / "NICE"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / "NG128.pdf"
    pdf_path.write_bytes(b"old")

    monkeypatch.setattr(path_config, "root", tmp_path)
    monkeypatch.setattr(path_config, "data_raw", data_root)
    monkeypatch.setattr(path_config, "data_processed",
                        tmp_path / "data" / "processed")
    _write_mapping(tmp_path, {"nice_id": "ng128", "source_name": "NICE"})

    monkeypatch.setenv("NICE_API_KEY", "test-key")
    monkeypatch.setenv("NICE_API_BASE_URL", "https://api.nice.test")
    monkeypatch.setenv("NICE_API_GUIDANCE_ENDPOINT", "/guidance/{nice_id}")

    remote = NiceGuideline(
        nice_id="ng128",
        content_type="guidance",
        pdf_url="https://cdn.nice.test/ng128.pdf",
        last_updated=datetime.utcnow().isoformat() + "Z",
        version="2",
    )

    with (
        patch.object(nice_updates.NiceSyndicationClient,
                     "fetch_guideline", return_value=remote),
        patch.object(nice_updates.NiceSyndicationClient,
                     "download_pdf", return_value=True),
        patch("src.ingestion.pipeline.run_ingestion",
              return_value={"files_failed": 0}),
    ):
        summary = nice_updates.update_nice_guidelines(
            data_root=data_root,
            db_url="postgresql://localhost/db",
        )

    assert summary["updated"] == 1
    assert summary["ingested"] == 1


def test_should_update_compares_versions(tmp_path: Path) -> None:
    pdf_path = tmp_path / "NG128.pdf"
    pdf_path.write_bytes(b"test")
    previous = {"version": "1"}
    remote = NiceGuideline(
        nice_id="ng128",
        content_type="guidance",
        pdf_url="https://cdn.nice.test/ng128.pdf",
        last_updated=None,
        version="2",
    )

    assert nice_updates._should_update(remote, previous, pdf_path) is True

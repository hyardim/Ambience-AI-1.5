from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.ingestion.cli import _configure_log_level, _resolve_db_url, cli

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

FAKE_SUMMARY = {
    "files_scanned": 2,
    "files_succeeded": 2,
    "files_failed": 0,
    "total_chunks": 10,
    "embeddings_succeeded": 10,
    "embeddings_failed": 0,
    "db": {"inserted": 10, "updated": 0, "skipped": 0, "failed": 0},
}

FAILED_SUMMARY = {
    **FAKE_SUMMARY,
    "files_succeeded": 1,
    "files_failed": 1,
}


def run_ingest(runner: CliRunner, args: list[str], input_path: str) -> Any:
    """Helper to invoke the ingest command with --input and --source-name always set."""
    return runner.invoke(
        cli,
        ["ingest", "--input", input_path, "--source-name", "NICE", *args],
    )

# -----------------------------------------------------------------------
# _resolve_db_url
# -----------------------------------------------------------------------


class TestResolveDbUrl:
    def test_returns_explicit_db_url(self) -> None:
        result = _resolve_db_url("postgresql://localhost/db", dry_run=False)
        assert result == "postgresql://localhost/db"

    def test_falls_back_to_env_var(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://env/db"}):
            result = _resolve_db_url(None, dry_run=False)
        assert result == "postgresql://env/db"

    def test_returns_none_on_dry_run_with_no_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = _resolve_db_url(None, dry_run=True)
        assert result is None

    def test_exits_if_no_url_and_not_dry_run(self) -> None:
        runner = CliRunner()
        with (
            patch.dict(os.environ, {}, clear=True),
            runner.isolated_filesystem(),
        ):
            import tempfile, pathlib
            with tempfile.TemporaryDirectory() as tmp:
                result = runner.invoke(
                    cli,
                    ["ingest", "--input", tmp, "--source-name", "NICE"],
                )
        assert result.exit_code == 1


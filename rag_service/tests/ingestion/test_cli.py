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


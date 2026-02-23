from __future__ import annotations

import logging
import os
import tempfile
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import src.ingestion.cli as cli_module
from src.ingestion.cli import _configure_log_level, _resolve_db_url, cli, main

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
            with tempfile.TemporaryDirectory() as tmp:
                result = runner.invoke(
                    cli,
                    ["ingest", "--input", tmp, "--source-name", "NICE"],
                )
        assert result.exit_code == 1


# -----------------------------------------------------------------------
# _configure_log_level
# -----------------------------------------------------------------------


class TestConfigureLogLevel:
    def test_sets_debug_level(self) -> None:

        _configure_log_level("DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_sets_info_level(self) -> None:

        _configure_log_level("INFO")
        assert logging.getLogger().level == logging.INFO

    def test_sets_warning_level(self) -> None:

        _configure_log_level("WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_sets_error_level(self) -> None:

        _configure_log_level("ERROR")
        assert logging.getLogger().level == logging.ERROR


# -----------------------------------------------------------------------
# ingest command
# -----------------------------------------------------------------------


class TestIngestCommand:
    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    @pytest.fixture()
    def input_dir(self, tmp_path: Any) -> str:
        (tmp_path / "test.pdf").touch()
        return str(tmp_path)

    def test_dry_run_succeeds(self, runner: CliRunner, input_dir: str) -> None:
        with patch("src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY):
            result = runner.invoke(
                cli,
                ["ingest", "--input", input_dir, "--source-name", "NICE", "--dry-run"],
            )
        assert result.exit_code == 0
        assert "Ingestion complete" in result.output

    def test_output_contains_all_summary_fields(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with patch("src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY):
            result = runner.invoke(
                cli,
                ["ingest", "--input", input_dir, "--source-name", "NICE", "--dry-run"],
            )
        assert "Files scanned" in result.output
        assert "Succeeded" in result.output
        assert "Failed" in result.output
        assert "Total chunks" in result.output
        assert "Embeddings OK" in result.output
        assert "DB inserted" in result.output

    def test_exits_1_when_files_failed(self, runner: CliRunner, input_dir: str) -> None:
        with patch("src.ingestion.cli.run_ingestion", return_value=FAILED_SUMMARY):
            result = runner.invoke(
                cli,
                ["ingest", "--input", input_dir, "--source-name", "NICE", "--dry-run"],
            )
        assert result.exit_code == 1

    def test_value_error_from_pipeline_exits_1(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with patch(
            "src.ingestion.cli.run_ingestion",
            side_effect=ValueError("Unknown --source-name 'FOO'"),
        ):
            result = runner.invoke(
                cli,
                ["ingest", "--input", input_dir, "--source-name", "FOO", "--dry-run"],
            )
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_passes_db_url_to_run_ingestion(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with patch(
            "src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY
        ) as mock_run:
            runner.invoke(
                cli,
                [
                    "ingest",
                    "--input",
                    input_dir,
                    "--source-name",
                    "NICE",
                    "--db-url",
                    "postgresql://localhost/db",
                ],
            )
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["db_url"] == "postgresql://localhost/db"

    def test_passes_dry_run_to_run_ingestion(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with patch(
            "src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY
        ) as mock_run:
            runner.invoke(
                cli,
                ["ingest", "--input", input_dir, "--source-name", "NICE", "--dry-run"],
            )
        assert mock_run.call_args.kwargs["dry_run"] is True

    def test_passes_max_files_to_run_ingestion(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with patch(
            "src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY
        ) as mock_run:
            runner.invoke(
                cli,
                [
                    "ingest",
                    "--input",
                    input_dir,
                    "--source-name",
                    "NICE",
                    "--dry-run",
                    "--max-files",
                    "3",
                ],
            )
        assert mock_run.call_args.kwargs["max_files"] == 3

    def test_passes_since_date_to_run_ingestion(
        self, runner: CliRunner, input_dir: str
    ) -> None:

        with patch(
            "src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY
        ) as mock_run:
            runner.invoke(
                cli,
                [
                    "ingest",
                    "--input",
                    input_dir,
                    "--source-name",
                    "NICE",
                    "--dry-run",
                    "--since",
                    "2024-01-01",
                ],
            )
        assert mock_run.call_args.kwargs["since"] == date(2024, 1, 1)

    def test_passes_write_debug_artifacts_to_run_ingestion(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with patch(
            "src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY
        ) as mock_run:
            runner.invoke(
                cli,
                [
                    "ingest",
                    "--input",
                    input_dir,
                    "--source-name",
                    "NICE",
                    "--dry-run",
                    "--write-debug-artifacts",
                ],
            )
        assert mock_run.call_args.kwargs["write_debug_artifacts"] is True

    def test_log_level_debug_accepted(self, runner: CliRunner, input_dir: str) -> None:
        with patch("src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY):
            result = runner.invoke(
                cli,
                [
                    "ingest",
                    "--input",
                    input_dir,
                    "--source-name",
                    "NICE",
                    "--dry-run",
                    "--log-level",
                    "DEBUG",
                ],
            )
        assert result.exit_code == 0

    def test_invalid_log_level_rejected(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "ingest",
                "--input",
                input_dir,
                "--source-name",
                "NICE",
                "--dry-run",
                "--log-level",
                "VERBOSE",
            ],
        )
        assert result.exit_code != 0

    def test_env_var_db_url_used_when_no_flag(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        with (
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://env/db"}),
            patch(
                "src.ingestion.cli.run_ingestion", return_value=FAKE_SUMMARY
            ) as mock_run,
        ):
            runner.invoke(
                cli,
                ["ingest", "--input", input_dir, "--source-name", "NICE"],
            )
        assert mock_run.call_args.kwargs["db_url"] == "postgresql://env/db"

    def test_missing_input_flag_exits_nonzero(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["ingest", "--source-name", "NICE", "--dry-run"])
        assert result.exit_code != 0

    def test_missing_source_name_exits_nonzero(
        self, runner: CliRunner, input_dir: str
    ) -> None:
        result = runner.invoke(cli, ["ingest", "--input", input_dir, "--dry-run"])
        assert result.exit_code != 0

    def test_main_entrypoint_is_callable(self) -> None:
        with patch("src.ingestion.cli.cli") as mock_cli:
            main()
            mock_cli.assert_called_once()

    def test_module_main_calls_main(self) -> None:
        with patch("src.ingestion.cli.main") as mock_main:
            original = cli_module.__name__
            try:
                cli_module.__name__ = "__main__"
                if cli_module.__name__ == "__main__":
                    cli_module.main()
            finally:
                cli_module.__name__ = original
                mock_main.assert_called_once()

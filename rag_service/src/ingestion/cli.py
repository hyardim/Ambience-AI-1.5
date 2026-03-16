from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

import click

from ..utils.logger import setup_logger
from .pipeline import run_ingestion
from .nice_updates import update_nice_guidelines

logger = setup_logger(__name__)


def _resolve_db_url(db_url: str | None, dry_run: bool) -> str | None:
    """Resolve DB URL from CLI flag or environment variable."""
    if db_url:
        return db_url
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    if not dry_run:
        click.echo(
            "ERROR: --db-url is required unless --dry-run is set. "
            "Set DATABASE_URL in your .env or pass --db-url.",
            err=True,
        )
        sys.exit(1)
    return None


def _configure_log_level(log_level: str) -> None:
    """Set root logger level from CLI flag."""
    numeric = getattr(logging, log_level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric)


@click.group()
def cli() -> None:
    """Ambience RAG ingestion CLI."""
    pass


@cli.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to a PDF file or folder of PDFs (recursive).",
)
@click.option(
    "--source-name",
    required=True,
    type=str,
    help="Source key from configs/sources.yaml (e.g. NICE, BSR).",
)
@click.option(
    "--db-url",
    default=None,
    type=str,
    help="Postgres connection string. Falls back to DATABASE_URL env var.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run pipeline without writing to database.",
)
@click.option(
    "--since",
    default=None,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Only ingest files modified after this date (YYYY-MM-DD).",
)
@click.option(
    "--max-files",
    default=None,
    type=int,
    help="Stop after processing N files.",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"],
                      case_sensitive=False),
    help="Logging level (default: INFO).",
)
@click.option(
    "--write-debug-artifacts",
    is_flag=True,
    default=False,
    help="Write intermediate pipeline outputs to data/debug/.",
)
def ingest(
    input_path: str,
    source_name: str,
    db_url: str | None,
    dry_run: bool,
    since: datetime | None,
    max_files: int | None,
    log_level: str,
    write_debug_artifacts: bool,
) -> None:
    """Run the ingestion pipeline on a PDF file or folder."""
    _configure_log_level(log_level)

    resolved_db_url = _resolve_db_url(db_url, dry_run)

    since_date: date | None = since.date() if since is not None else None

    if dry_run:
        logger.info("DRY RUN — no database writes will occur")

    try:
        summary = run_ingestion(
            input_path=Path(input_path),
            source_name=source_name,
            db_url=resolved_db_url,
            dry_run=dry_run,
            since=since_date,
            max_files=max_files,
            write_debug_artifacts=write_debug_artifacts,
        )
    except ValueError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    click.echo(
        f"\nIngestion complete:\n"
        f"  Files scanned:  {summary['files_scanned']}\n"
        f"  Succeeded:      {summary['files_succeeded']}\n"
        f"  Failed:         {summary['files_failed']}\n"
        f"  Total chunks:   {summary['total_chunks']}\n"
        f"  Embeddings OK:  {summary['embeddings_succeeded']}\n"
        f"  Embeddings ERR: {summary['embeddings_failed']}\n"
        f"  DB inserted:    {summary['db']['inserted']}\n"
        f"  DB updated:     {summary['db']['updated']}\n"
        f"  DB skipped:     {summary['db']['skipped']}\n"
        f"  DB failed:      {summary['db']['failed']}"
    )

    if summary["files_failed"] > 0:
        sys.exit(1)


@cli.command("update-nice")
@click.option(
    "--raw-dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Override data/raw root directory.",
)
@click.option(
    "--db-url",
    default=None,
    type=str,
    help="Postgres connection string. Falls back to DATABASE_URL env var.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Check for updates without downloading or ingesting.",
)
@click.option(
    "--max-files",
    default=None,
    type=int,
    help="Stop after processing N files.",
)
@click.option(
    "--skip-ingest",
    is_flag=True,
    default=False,
    help="Download updates but skip ingestion.",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"],
                      case_sensitive=False),
    help="Logging level (default: INFO).",
)
def update_nice(
    raw_dir: str | None,
    db_url: str | None,
    dry_run: bool,
    max_files: int | None,
    skip_ingest: bool,
    log_level: str,
) -> None:
    """Check NICE Syndication API for updated guidelines."""
    _configure_log_level(log_level)

    resolved_db_url = None
    if not skip_ingest:
        resolved_db_url = _resolve_db_url(db_url, dry_run)

    summary = update_nice_guidelines(
        data_root=Path(raw_dir) if raw_dir else None,
        db_url=resolved_db_url,
        dry_run=dry_run,
        max_files=max_files,
        ingest=not skip_ingest,
    )

    click.echo(
        f"\nNICE update summary:\n"
        f"  Scanned:   {summary['scanned']}\n"
        f"  Matched:   {summary['matched']}\n"
        f"  Updated:   {summary['updated']}\n"
        f"  Ingested:  {summary.get('ingested', 0)}\n"
        f"  Skipped:   {summary['skipped']}\n"
        f"  Failed:    {summary.get('failed', 0)}"
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

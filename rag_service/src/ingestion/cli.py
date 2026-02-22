from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path

import click

from ..utils.logger import setup_logger
from .pipeline import run_ingestion

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

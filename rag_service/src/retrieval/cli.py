from __future__ import annotations

import os
import sys

import click
from dotenv import load_dotenv

from ..utils.logger import setup_logger
from .citation import format_citation
from .query import RetrievalError
from .retrieve import retrieve

logger = setup_logger(__name__)

_SEPARATOR = "─" * 49

def _resolve_db_url(db_url: str | None) -> str | None:
    if db_url:
        return db_url
    if url := os.environ.get("DATABASE_URL"):
        return url
    load_dotenv()
    return os.environ.get("DATABASE_URL")

@click.group()
def main() -> None:
    """Retrieval pipeline CLI."""


@main.command()
@click.option("--query", required=True, help="Query string")
@click.option("--db-url", default=None, help="PostgreSQL connection string")
@click.option("--top-k", default=5, show_default=True, help="Number of results")
@click.option("--specialty", default=None, help="Filter by specialty")
@click.option("--source-name", default=None, help="Filter by source name")
@click.option("--doc-type", default=None, help="Filter by document type")
@click.option("--score-threshold", default=0.3, show_default=True, help="Min score threshold")
@click.option("--expand-query", is_flag=True, default=False, help="Expand query with synonyms")
@click.option("--write-debug-artifacts", is_flag=True, default=False, help="Write debug artifacts")
def query(
    query: str,
    db_url: str | None,
    top_k: int,
    specialty: str | None,
    source_name: str | None,
    doc_type: str | None,
    score_threshold: float,
    expand_query: bool,
    write_debug_artifacts: bool,
) -> None:
    """Run retrieval for a query and print results."""
    pass
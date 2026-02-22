from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from ..utils.logger import setup_logger
from .chunk import chunk_document
from .clean import clean_document
from .embed import embed_chunks
from .extract import extract_raw_document
from .metadata import attach_metadata
from .section_detect import add_section_metadata
from .store import store_chunks
from .table_detect import detect_and_convert_tables

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_VERSION = "main"
DEFAULT_EMBEDDING_DIMENSIONS = 384
DEFAULT_CHUNK_SIZE = 450
DEFAULT_OVERLAP = 0.15
DEFAULT_LOG_LEVEL = "INFO"

STAGE_EXTRACT = "EXTRACT"
STAGE_CLEAN = "CLEAN"
STAGE_SECTION = "SECTION"
STAGE_TABLE = "TABLE"
STAGE_METADATA = "METADATA"
STAGE_CHUNK = "CHUNK"
STAGE_EMBED = "EMBED"
STAGE_STORE = "STORE"

# -----------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""

    def __init__(self, stage: str, pdf_path: str, message: str) -> None:
        self.stage = stage
        self.pdf_path = pdf_path
        self.message = message
        super().__init__(f"{stage} | {pdf_path} | {message}")

# -----------------------------------------------------------------------
# Debug artifacts
# -----------------------------------------------------------------------


def _strip_embeddings(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of doc with embedding vectors replaced by metadata."""
    import copy

    doc_copy = copy.deepcopy(doc)
    for chunk in doc_copy.get("chunks", []):
        if "embedding" in chunk:
            chunk["embedding"] = "<stripped>"
    return doc_copy


def _write_debug_artifact(
    doc_id: str,
    stage_num: int,
    stage_name: str,
    data: dict[str, Any],
) -> None:
    """Write a pipeline stage output to data/debug/<doc_id>/<stage>.json."""
    from ..config import path_config

    debug_dir = path_config.data_debug / doc_id
    debug_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{stage_num:02d}_{stage_name}.json"
    path = debug_dir / filename

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug(f"Debug artifact written: {path}")
    except Exception as e:
        logger.warning(f"Failed to write debug artifact {path}: {e}")

# -----------------------------------------------------------------------
# Single file pipeline
# -----------------------------------------------------------------------

def run_pipeline(
    pdf_path: Path,
    source_info: dict[str, Any],
    db_url: str | None,
    dry_run: bool,
    write_debug_artifacts: bool,
) -> dict[str, Any]:
    """
    Run all pipeline stages for a single PDF.

    Args:
        pdf_path: Path to the PDF file
        source_info: Source metadata dict from sources.yaml
        db_url: Postgres connection string, or None if dry_run
        dry_run: If True, skip DB write
        write_debug_artifacts: If True, write intermediate JSON outputs

    Returns:
        Per-file report dict with counts and metrics

    Raises:
        PipelineError: On stage failure, with stage label attached
    """
    path_str = str(pdf_path)
    source_info = {**source_info, "source_path": path_str}

    # ---- Stage 1: Extract ----
    try:
        raw_doc = extract_raw_document(pdf_path)
    except Exception as e:
        raise PipelineError(STAGE_EXTRACT, path_str, str(e)) from e

    if write_debug_artifacts:
        _write_debug_artifact("pending", 1, "raw", raw_doc)

    # ---- Stage 2: Clean ----
    try:
        clean_doc = clean_document(raw_doc)
    except Exception as e:
        raise PipelineError(STAGE_CLEAN, path_str, str(e)) from e

    if write_debug_artifacts:
        _write_debug_artifact("pending", 2, "clean", clean_doc)

    # ---- Stage 3: Section detect ----
    try:
        sectioned_doc = add_section_metadata(clean_doc)
    except Exception as e:
        raise PipelineError(STAGE_SECTION, path_str, str(e)) from e

    if write_debug_artifacts:
        _write_debug_artifact("pending", 3, "sectioned", sectioned_doc)

    # ---- Stage 4: Table detect ----
    try:
        table_aware_doc = detect_and_convert_tables(sectioned_doc, pdf_path=path_str)
    except Exception as e:
        raise PipelineError(STAGE_TABLE, path_str, str(e)) from e

    if write_debug_artifacts:
        _write_debug_artifact("pending", 4, "table_aware", table_aware_doc)

    # ---- Stage 5: Metadata ----
    try:
        metadata_doc = attach_metadata(table_aware_doc, source_info)
    except Exception as e:
        raise PipelineError(STAGE_METADATA, path_str, str(e)) from e

    doc_id = metadata_doc.get("doc_meta", {}).get("doc_id", "unknown")

    if write_debug_artifacts:
        _write_debug_artifact(doc_id, 5, "metadata", metadata_doc)
        # Retroactively rename earlier artifacts now that we have doc_id
        _backfill_debug_artifacts(doc_id)

    # ---- Stage 6: Chunk ----
    try:
        chunked_doc = chunk_document(metadata_doc)
    except Exception as e:
        raise PipelineError(STAGE_CHUNK, path_str, str(e)) from e

    if write_debug_artifacts:
        _write_debug_artifact(doc_id, 6, "chunked", chunked_doc)

    # ---- Stage 7: Embed ----
    try:
        embedded_doc = embed_chunks(chunked_doc)
    except Exception as e:
        raise PipelineError(STAGE_EMBED, path_str, str(e)) from e

    if write_debug_artifacts:
        _write_debug_artifact(doc_id, 7, "embedded_meta", _strip_embeddings(embedded_doc))

    # ---- Stage 8: Store ----
    db_report: dict[str, int] = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
    }
    if not dry_run:
        try:
            db_report = store_chunks(embedded_doc, db_url=db_url)
        except Exception as e:
            raise PipelineError(STAGE_STORE, path_str, str(e)) from e

    # ---- Build per-file report ----
    chunks = embedded_doc.get("chunks", [])
    n_success = sum(1 for c in chunks if c.get("embedding_status") == "success")
    n_failed = sum(1 for c in chunks if c.get("embedding_status") == "failed")

    pages = embedded_doc.get("pages", [])
    n_tables = sum(
        1
        for page in pages
        for block in page.get("blocks", [])
        if block.get("content_type") == "table"
    )
    n_headings = sum(
        1
        for page in pages
        for block in page.get("blocks", [])
        if block.get("is_heading", False)
    )

    report = {
        "file": path_str,
        "doc_id": doc_id,
        "pages": embedded_doc.get("num_pages", 0),
        "chunks": len(chunks),
        "embeddings_succeeded": n_success,
        "embeddings_failed": n_failed,
        "headings_detected": n_headings,
        "tables_detected": n_tables,
        "db": db_report,
    }

    logger.info(
        f"Completed {pdf_path.name}: "
        f"pages={report['pages']} "
        f"chunks={report['chunks']} "
        f"embeddings={n_success}/{n_success + n_failed} "
        f"db=inserted:{db_report['inserted']} "
        f"updated:{db_report['updated']} "
        f"skipped:{db_report['skipped']} "
        f"failed:{db_report['failed']}"
    )

    return report

def _backfill_debug_artifacts(doc_id: str) -> None:
    """Rename debug artifacts written under 'pending' to the real doc_id."""
    from ..config import path_config

    pending_dir = path_config.data_debug / "pending"
    if not pending_dir.exists():
        return

    real_dir = path_config.data_debug / doc_id
    real_dir.mkdir(parents=True, exist_ok=True)

    for artifact in pending_dir.iterdir():
        target = real_dir / artifact.name
        if not target.exists():
            artifact.rename(target)

    try:
        pending_dir.rmdir()
    except OSError:
        pass

# -----------------------------------------------------------------------
# Multi-file orchestration
# -----------------------------------------------------------------------


def discover_pdfs(
    input_path: Path,
    since: date | None = None,
    max_files: int | None = None,
) -> list[Path]:
    """
    Discover PDF files from a path (file or folder, recursive).

    Args:
        input_path: Path to PDF file or folder
        since: Only include files modified after this date
        max_files: Maximum number of files to return

    Returns:
        List of PDF paths sorted by modification time (oldest first)
    """
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file is not a PDF: {input_path}")
        pdfs = [input_path]
    elif input_path.is_dir():
        pdfs = sorted(
            input_path.rglob("*.pdf"),
            key=lambda p: p.stat().st_mtime,
        )
    else:
        raise ValueError(f"Input path does not exist: {input_path}")

    if since is not None:
        pdfs = [
            p
            for p in pdfs
            if date.fromtimestamp(p.stat().st_mtime) > since
        ]

    if max_files is not None:
        pdfs = pdfs[:max_files]

    return pdfs

def load_sources(sources_path: Path) -> dict[str, Any]:
    """Load sources.yaml and return as dict."""
    import yaml

    with open(sources_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_ingestion_config(config_path: Path) -> dict[str, Any]:
    """Load ingestion.yaml if it exists, return empty dict otherwise."""
    import yaml

    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def run_ingestion(
    input_path: Path,
    source_name: str,
    db_url: str | None,
    dry_run: bool = False,
    since: date | None = None,
    max_files: int | None = None,
    write_debug_artifacts: bool = False,
) -> dict[str, Any]:
    """
    Discover PDFs, run pipeline per file, return summary report.

    Args:
        input_path: Path to PDF file or folder
        source_name: Key into configs/sources.yaml
        db_url: Postgres connection string, or None
        dry_run: If True, skip DB writes
        since: Only process files modified after this date
        max_files: Maximum number of files to process
        write_debug_artifacts: If True, write intermediate JSON outputs

    Returns:
        Summary report dict
    """
    from ..config import path_config

    sources_path = Path("configs/sources.yaml")
    config_path = Path("configs/ingestion.yaml")

    # Load source metadata
    sources = load_sources(sources_path)
    if source_name not in sources:
        raise ValueError(
            f"Unknown --source-name '{source_name}'. "
            f"Available: {sorted(sources.keys())}. "
            f"Check configs/sources.yaml."
        )
    source_info = sources[source_name]

    # Load ingestion config (optional)
    ingestion_config = load_ingestion_config(config_path)
    logger.debug(f"Ingestion config loaded: {ingestion_config}")

    # Discover PDFs
    pdfs = discover_pdfs(input_path, since=since, max_files=max_files)
    logger.info(f"Found {len(pdfs)} PDF(s) to process from {input_path}")

    if not pdfs:
        logger.warning("No PDFs found matching criteria.")
        return {
            "files_scanned": 0,
            "files_succeeded": 0,
            "files_failed": 0,
            "total_chunks": 0,
            "embeddings_succeeded": 0,
            "embeddings_failed": 0,
            "db": {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0},
        }

    # Initialise summary
    summary: dict[str, Any] = {
        "files_scanned": len(pdfs),
        "files_succeeded": 0,
        "files_failed": 0,
        "total_chunks": 0,
        "embeddings_succeeded": 0,
        "embeddings_failed": 0,
        "db": {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0},
    }

    for pdf_path in pdfs:
        logger.info(f"Processing: {pdf_path}")
        try:
            report = run_pipeline(
                pdf_path=pdf_path,
                source_info=source_info,
                db_url=db_url,
                dry_run=dry_run,
                write_debug_artifacts=write_debug_artifacts,
            )
            summary["files_succeeded"] += 1
            summary["total_chunks"] += report["chunks"]
            summary["embeddings_succeeded"] += report["embeddings_succeeded"]
            summary["embeddings_failed"] += report["embeddings_failed"]
            for key in ("inserted", "updated", "skipped", "failed"):
                summary["db"][key] += report["db"][key]

        except PipelineError as e:
            summary["files_failed"] += 1
            logger.error(f"ERROR | {e.stage} | {e.pdf_path} | {e.message}")
        except Exception as e:
            summary["files_failed"] += 1
            logger.error(f"ERROR | UNKNOWN | {pdf_path} | {e}")

    logger.info(
        f"Ingestion complete: "
        f"scanned={summary['files_scanned']} "
        f"succeeded={summary['files_succeeded']} "
        f"failed={summary['files_failed']} "
        f"chunks={summary['total_chunks']} "
        f"db=inserted:{summary['db']['inserted']} "
        f"updated:{summary['db']['updated']} "
        f"skipped:{summary['db']['skipped']}"
    )

    return summary

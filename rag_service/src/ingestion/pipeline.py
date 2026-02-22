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

from __future__ import annotations

import json
from typing import Any

from pgvector.psycopg2 import register_vector

from ...src.utils.db import db
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

def _build_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    """Extract and return the metadata jsonb payload from a chunk."""
    return {
        "source_name": chunk.get("citation", {}).get("source_name", ""),
        "title": chunk.get("citation", {}).get("title", ""),
        "section_path": chunk.get("section_path", []),
        "section_title": chunk.get("section_title", ""),
        "page_start": chunk.get("page_start", 0),
        "page_end": chunk.get("page_end", 0),
        "citation": chunk.get("citation", {}),
    }

def _metadata_json(metadata: dict[str, Any]) -> str:
    """Serialise metadata to sorted JSON string for comparison."""
    return json.dumps(metadata, sort_keys=True)
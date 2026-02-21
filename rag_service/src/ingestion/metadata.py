from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_SPECIALTIES = {"neurology", "rheumatology"}
VALID_SOURCE_NAMES = {"NICE", "BSR", "Others"}
VALID_DOC_TYPES = {"guideline", "protocol", "policy", "standard"}

class MetadataValidationError(Exception):
    """Raised when metadata validation fails."""
    pass

def attach_metadata(
    table_aware_doc: dict[str, Any],
    source_info: dict[str, Any],
) -> dict[str, Any]:
    """
    Attach complete metadata at document and block levels.

    Args:
        table_aware_doc: TableAwareDocument dict from table_detect.py
        source_info: Dict containing external metadata (see source_info schema)

    Returns:
        dict: MetadataDocument with doc_meta and block_uid on every block

    Raises:
        MetadataValidationError: If required metadata is missing or invalid

    Processing steps:
        1. Infer specialty/source_name from path if not provided
        2. Validate source_info
        3. Extract PDF metadata from source file
        4. Generate doc_id (stable, content-based)
        5. Generate doc_version (detects updates)
        6. Extract or infer title
        7. Create doc_meta object
        8. For each block, generate block_uid
        9. Validate all metadata
    """
    pass

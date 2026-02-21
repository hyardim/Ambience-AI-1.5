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


def infer_from_path(source_path: str) -> dict[str, str]:
    """Infer specialty and source_name from file path structure.

    Expected path pattern: .../raw/{specialty}/{source_name}/{filename}.pdf

    Args:
        source_path: File path to the PDF

    Returns:
        Dict with 'specialty' and 'source_name' if inferable, else empty strings
    """
    parts = Path(source_path).parts
    try:
        raw_index = parts.index("raw")
        return {
            "specialty": parts[raw_index + 1],
            "source_name": parts[raw_index + 2],
        }
    except (ValueError, IndexError):
        return {"specialty": "", "source_name": ""}
  
def validate_source_info(source_info: dict[str, Any]) -> None:
    """Validate source_info fields.

    Args:
        source_info: Caller-supplied source info dict

    Raises:
        MetadataValidationError: If any required field is missing or invalid
    """
    required = ["source_name", "source_path", "doc_type", "specialty"]
    for field in required:
        if not source_info.get(field):
            raise MetadataValidationError(
                f"source_info missing required field: {field}"
            )

    if source_info["specialty"] not in VALID_SPECIALTIES:
        raise MetadataValidationError(
            f"Invalid specialty '{source_info['specialty']}'. "
            f"Must be one of: {VALID_SPECIALTIES}"
        )

    if source_info["source_name"] not in VALID_SOURCE_NAMES:
        raise MetadataValidationError(
            f"Invalid source_name '{source_info['source_name']}'. "
            f"Must be one of: {VALID_SOURCE_NAMES}"
        )

    if source_info["doc_type"] not in VALID_DOC_TYPES:
        raise MetadataValidationError(
            f"Invalid doc_type '{source_info['doc_type']}'. "
            f"Must be one of: {VALID_DOC_TYPES}"
        )

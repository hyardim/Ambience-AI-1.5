from __future__ import annotations

import re
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

def detect_and_convert_tables(
    sectioned_doc: dict[str, Any],
    pdf_path: str,
) -> dict[str, Any]:
    """
    Detect tables and convert to Markdown chunks.

    Args:
        sectioned_doc: SectionedDocument dict from section_detect.py
        pdf_path: Path to original PDF file (required for PyMuPDF table detection)

    Returns:
        dict: TableAwareDocument with:
            - Tables converted to Markdown
            - All blocks tagged with content_type
            - Table blocks include table_title if caption detected

    Processing steps:
        1. Use PyMuPDF to detect tables by visual layout
        2. Apply pipe-delimiter heuristic for borderless tables
        3. Detect table captions (table_title)
        4. Convert tables to Markdown
        5. Map tables to document blocks
        6. Tag all blocks with content_type
    """
    pass


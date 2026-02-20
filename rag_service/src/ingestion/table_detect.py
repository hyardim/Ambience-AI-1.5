from __future__ import annotations

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


def detect_tables_with_pymupdf(
    pdf_path: str,
    page_num: int,
) -> list[dict[str, Any]]:
    """Use PyMuPDF to detect tables on a page.

    Args:
        pdf_path: Path to the PDF file
        page_num: 1-indexed page number

    Returns:
        List of dicts with keys: cells, bbox, page_number
    """
    results: list[dict[str, Any]] = []

    try:
        with fitz.open(pdf_path) as doc:
            if page_num < 1 or page_num > doc.page_count:
                logger.warning(f"Page {page_num} out of range for {pdf_path}")
                return results

            page = doc[page_num - 1]
            tables = page.find_tables()

            for table in tables:
                cells = table.extract()
                bbox = list(table.bbox)
                results.append(
                    {
                        "cells": cells,
                        "bbox": bbox,
                        "page_number": page_num,
                    }
                )

    except Exception as e:
        logger.warning(
            f"PyMuPDF table detection failed for {pdf_path} page {page_num}: {e}"
        )

    return results

from __future__ import annotations

import re
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

CAPTION_PATTERN = re.compile(r"^Table\s+\d+[\.:]\s*.+", re.IGNORECASE)
CAPTION_PROXIMITY_PX = 50
CELL_MAX_LENGTH = 100
MIN_PIPE_COUNT = 3
MIN_PIPE_LINES = 2


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

def find_table_caption(
    table_bbox: list[float],
    page_blocks: list[dict[str, Any]],
) -> str | None:
    """Find table_title for a table by checking blocks above its bbox.

    Looks for blocks ending within 50px above the table top that either
    match the 'Table N:' pattern or are bold text.

    Args:
        table_bbox: [x0, y0, x1, y1] bounding box of table
        page_blocks: List of block dicts for the page

    Returns:
        Caption string, or None if not found
    """
    table_top = table_bbox[1]

    for block in page_blocks:
        block_bottom = block["bbox"][3]
        if block_bottom < table_top and table_top - block_bottom < CAPTION_PROXIMITY_PX:
            text = block.get("text", "").strip()
            if CAPTION_PATTERN.match(text):
                return text
            if block.get("is_bold", False):
                return text

    return None

def cells_to_markdown(
    cells: list[list[str]],
    table_title: str | None = None,
) -> str:
    """Convert table cells to GitHub-flavored Markdown.

    Args:
        cells: List of rows, each row is list of cell strings
        table_title: Optional caption included as HTML comment

    Returns:
        Markdown-formatted table string, or empty string if no data
    """
    pass


def detect_header_row(cells: list[list[str]]) -> bool:
    """Determine if first row should be treated as header.

    Returns True if >50% of first row cells are non-numeric.

    Args:
        cells: Normalized cell data

    Returns:
        True if first row is a header
    """
    if not cells or len(cells) < 2:
        return False

    first_row = cells[0]
    if not first_row:
        return False

    non_numeric = sum(
        1 for cell in first_row
        if cell and not cell.replace(".", "").replace("-", "").isdigit()
    )
    return non_numeric / len(first_row) > 0.5

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
        2. Detect table captions (table_title)
        3. Convert tables to Markdown
        4. Map tables to document blocks
        5. Apply pipe-delimiter heuristic for borderless tables
        6. Tag all blocks with content_type
    """
    pages = sectioned_doc.get("pages", [])
    total_pymupdf = 0
    total_heuristic = 0
    total_captions = 0

    for page in pages:
        page_num = page["page_number"]
        blocks = page["blocks"]

        # Step 1: detect tables with PyMuPDF
        detected_tables = detect_tables_with_pymupdf(pdf_path, page_num)
        total_pymupdf += len(detected_tables)

        # Steps 2-5: process each detected table
        for table_info in detected_tables:
            cells = table_info["cells"]
            table_bbox = table_info["bbox"]

            # Step 2: find caption
            table_title = find_table_caption(table_bbox, blocks)
            if table_title:
                total_captions += 1

            # Step 3: convert to Markdown
            markdown = cells_to_markdown(cells, table_title)
            if not markdown:
                continue

            # Step 4: map to blocks
            overlapping = find_overlapping_blocks(table_bbox, blocks)
            if not overlapping:
                logger.warning(
                    f"Page {page_num}: no overlapping blocks for table at {table_bbox}"
                )
                continue

            section_path = overlapping[0].get("section_path", ["Unknown"])
            section_title = overlapping[0].get("section_title", "Unknown")
            original_position = blocks.index(overlapping[0])

            for block in overlapping:
                block["is_table_content"] = True

            table_chunk: dict[str, Any] = {
                "content_type": "table",
                "text": markdown,
                "table_title": table_title,
                "section_path": section_path,
                "section_title": section_title,
                "page_number": page_num,
                "bbox": table_bbox,
                "is_heading": False,
                "include_in_chunks": overlapping[0].get("include_in_chunks", True),
            }

            # Remove overlapping blocks and insert table chunk
            page["blocks"] = [b for b in blocks if not b.get("is_table_content")]
            page["blocks"].insert(original_position, table_chunk)
            blocks = page["blocks"]

        # Step 5: heuristic fallback for pipe-delimited tables
        n_heuristic = 0
        for block in page["blocks"]:
            if block.get("content_type") != "table" and _is_pipe_table_block(
                block.get("text", "")
            ):
                block["content_type"] = "table"
                block["table_title"] = None
                block["page_number"] = page_num
                n_heuristic += 1
        total_heuristic += n_heuristic

        # Step 6: tag all remaining blocks
        for block in page["blocks"]:
            if "content_type" not in block:
                if block.get("is_heading", False):
                    block["content_type"] = "heading"
                else:
                    block["content_type"] = "text"

    logger.info(
        f"Total: {total_pymupdf} tables via PyMuPDF, "
        f"{total_heuristic} via heuristic, "
        f"{total_captions} captions found"
    )

    sample_tables = next(
        (
            b["text"]
            for page in pages
            for b in page["blocks"]
            if b.get("content_type") == "table"
        ),
        None,
    )
    if sample_tables:
        logger.debug(f"Sample Markdown table:\n{sample_tables}")

    return {
        **sectioned_doc,
        "pages": pages,
    }


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
            finder = page.find_tables()
            tables = getattr(finder, "tables", finder)

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
    best_text: str | None = None
    best_distance = float("inf")

    for block in page_blocks:
        block_bottom = block["bbox"][3]
        if block_bottom < table_top:
            distance = table_top - block_bottom
            if distance < CAPTION_PROXIMITY_PX:
                text = block.get("text", "").strip()
                if CAPTION_PATTERN.match(text) or block.get("is_bold", False):
                    if distance < best_distance:
                        best_distance = distance
                        best_text = str(text)

    return best_text


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
    if not cells:
        return ""

    # Normalize all cells
    normalized = [[_normalize_cell(c) for c in row] for row in cells]

    # Determine column count
    max_cols = max(len(row) for row in normalized)
    if max_cols == 0:
        return ""

    # Pad rows
    for row in normalized:
        while len(row) < max_cols:
            row.append("")

    if all(cell == "" for row in normalized for cell in row):
        return ""

    # Single-column → bulleted list
    if max_cols == 1:
        items = [row[0] for row in normalized if row[0]]
        lines = []
        if table_title:
            lines.append(f"<!-- {table_title} -->")
        lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)

    has_header = detect_header_row(normalized)

    if has_header:
        header_row = normalized[0]
        data_rows = normalized[1:]
    else:
        header_row = [f"Column {i + 1}" for i in range(max_cols)]
        data_rows = normalized

    lines = []
    if table_title:
        lines.append(f"<!-- {table_title} -->")

    lines.append("| " + " | ".join(header_row) + " |")
    lines.append("|" + "|".join(["---"] * max_cols) + "|")
    for row in data_rows:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


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
        1
        for cell in first_row
        if cell and not cell.replace(".", "").replace("-", "").isdigit()
    )
    return non_numeric / len(first_row) > 0.5


def find_overlapping_blocks(
    table_bbox: list[float],
    blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find blocks whose bounding box overlaps with the table bbox.

    Args:
        table_bbox: [x0, y0, x1, y1] bounding box of table
        blocks: List of block dicts

    Returns:
        List of overlapping blocks in original order
    """
    return [b for b in blocks if bboxes_overlap(table_bbox, b["bbox"])]


def bboxes_overlap(
    bbox1: list[float],
    bbox2: list[float],
) -> bool:
    """Check if two bounding boxes overlap.

    Args:
        bbox1: [x0, y0, x1, y1]
        bbox2: [x0, y0, x1, y1]

    Returns:
        True if boxes overlap
    """
    return not (
        bbox1[2] <= bbox2[0]
        or bbox2[2] <= bbox1[0]
        or bbox1[3] <= bbox2[1]
        or bbox2[3] <= bbox1[1]
    )


def _normalize_cell(cell: Any) -> str:
    """Normalize a table cell value.

    - None → ""
    - Newlines → " / "
    - Pipe chars → "\\|"
    - Trim whitespace
    - Truncate at 100 chars

    Args:
        cell: Raw cell value

    Returns:
        Normalized cell string
    """
    if cell is None:
        return ""
    text = str(cell).replace("\n", " / ").replace("\r", "")
    text = text.replace("|", "\\|")
    text = text.strip()
    if len(text) > CELL_MAX_LENGTH:
        text = text[: CELL_MAX_LENGTH - 3] + "..."
    return text


def _is_pipe_table_block(text: str) -> bool:
    """Check if block text looks like a pipe-delimited table.

    Requires 2+ lines each containing 3+ pipe characters.

    Args:
        text: Block text

    Returns:
        True if block appears to be a pipe-delimited table
    """
    lines = text.split("\n")
    pipe_lines = [line for line in lines if line.count("|") >= MIN_PIPE_COUNT]
    return len(pipe_lines) >= MIN_PIPE_LINES

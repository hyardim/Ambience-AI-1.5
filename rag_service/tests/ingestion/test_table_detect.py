from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.table_detect import (
    _is_pipe_table_block,
    _normalize_cell,
    bboxes_overlap,
    cells_to_markdown,
    detect_and_convert_tables,
    detect_header_row,
    detect_tables_with_pymupdf,
    find_overlapping_blocks,
    find_table_caption,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def make_block(
    text: str,
    block_id: int = 0,
    bbox: list[float] | None = None,
    is_bold: bool = False,
    is_heading: bool = False,
    section_path: list[str] | None = None,
    section_title: str = "Introduction",
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "text": text,
        "bbox": bbox or [10.0, 100.0, 500.0, 120.0],
        "is_bold": is_bold,
        "is_heading": is_heading,
        "font_size": 12.0,
        "font_name": "Arial",
        "section_path": section_path or ["Introduction"],
        "section_title": section_title,
        "include_in_chunks": True,
    }


def make_page(
    page_number: int,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if blocks is None:
        blocks = [make_block("Some content")]
    return {"page_number": page_number, "blocks": blocks}


def make_sectioned_doc(
    pages: list[dict[str, Any]] | None = None,
    source_path: str = "test.pdf",
) -> dict[str, Any]:
    if pages is None:
        pages = [make_page(1)]
    return {
        "source_path": source_path,
        "num_pages": len(pages),
        "needs_ocr": False,
        "pages": pages,
    }


def make_fitz_table(
    cells: list[list[str]],
    bbox: tuple[float, float, float, float] = (50.0, 200.0, 400.0, 350.0),
) -> MagicMock:
    table = MagicMock()
    table.extract.return_value = cells
    table.bbox = bbox
    return table


def make_fitz_page(tables: list[MagicMock] | None = None) -> MagicMock:
    page = MagicMock()
    page.find_tables.return_value = tables or []
    return page


def make_fitz_doc(
    pages: list[MagicMock] | None = None,
    page_count: int = 1,
) -> MagicMock:
    doc = MagicMock()
    doc.page_count = page_count
    if pages:
        doc.__getitem__ = MagicMock(side_effect=lambda i: pages[i])
    doc.__enter__ = MagicMock(return_value=doc)
    doc.__exit__ = MagicMock(return_value=False)
    return doc

# -----------------------------------------------------------------------
# bboxes_overlap
# -----------------------------------------------------------------------

class TestBboxesOverlap:
    def test_overlapping_boxes(self) -> None:
        assert bboxes_overlap([0, 0, 100, 100], [50, 50, 150, 150]) is True

    def test_non_overlapping_horizontal(self) -> None:
        assert bboxes_overlap([0, 0, 100, 100], [200, 0, 300, 100]) is False

    def test_non_overlapping_vertical(self) -> None:
        assert bboxes_overlap([0, 0, 100, 100], [0, 200, 100, 300]) is False

    def test_touching_edge_not_overlap(self) -> None:
        assert bboxes_overlap([0, 0, 100, 100], [100, 0, 200, 100]) is False

    def test_one_inside_other(self) -> None:
        assert bboxes_overlap([0, 0, 200, 200], [50, 50, 150, 150]) is True

    def test_identical_boxes(self) -> None:
        assert bboxes_overlap([0, 0, 100, 100], [0, 0, 100, 100]) is True


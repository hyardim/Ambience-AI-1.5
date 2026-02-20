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

# -----------------------------------------------------------------------
# find_overlapping_blocks
# -----------------------------------------------------------------------

class TestFindOverlappingBlocks:
    def test_finds_overlapping_block(self) -> None:
        blocks = [make_block("text", bbox=[50.0, 200.0, 400.0, 220.0])]
        result = find_overlapping_blocks([40.0, 190.0, 410.0, 360.0], blocks)
        assert len(result) == 1

    def test_non_overlapping_block_excluded(self) -> None:
        blocks = [make_block("text", bbox=[10.0, 10.0, 100.0, 30.0])]
        result = find_overlapping_blocks([200.0, 200.0, 400.0, 400.0], blocks)
        assert len(result) == 0

    def test_multiple_overlapping_blocks(self) -> None:
        blocks = [
            make_block("a", block_id=0, bbox=[50.0, 200.0, 400.0, 220.0]),
            make_block("b", block_id=1, bbox=[50.0, 230.0, 400.0, 250.0]),
            make_block("c", block_id=2, bbox=[10.0, 10.0, 100.0, 30.0]),
        ]
        result = find_overlapping_blocks([40.0, 190.0, 410.0, 360.0], blocks)
        assert len(result) == 2

    def test_empty_blocks(self) -> None:
        assert find_overlapping_blocks([0.0, 0.0, 100.0, 100.0], []) == []

# -----------------------------------------------------------------------
# _normalize_cell
# -----------------------------------------------------------------------

class TestNormalizeCell:
    def test_none_returns_empty(self) -> None:
        assert _normalize_cell(None) == ""

    def test_newline_replaced(self) -> None:
        assert _normalize_cell("a\nb") == "a / b"

    def test_pipe_escaped(self) -> None:
        assert _normalize_cell("a | b") == r"a \| b"

    def test_whitespace_trimmed(self) -> None:
        assert _normalize_cell("  hello  ") == "hello"

    def test_truncated_at_100(self) -> None:
        long_text = "a" * 105
        result = _normalize_cell(long_text)
        assert len(result) == 100
        assert result.endswith("...")

    def test_exactly_100_not_truncated(self) -> None:
        text = "a" * 100
        assert _normalize_cell(text) == text

    def test_normal_text_unchanged(self) -> None:
        assert _normalize_cell("hello world") == "hello world"

    def test_integer_input(self) -> None:
        assert _normalize_cell(42) == "42"

# -----------------------------------------------------------------------
# detect_header_row
# -----------------------------------------------------------------------

class TestDetectHeaderRow:
    def test_text_header_detected(self) -> None:
        cells = [["Drug", "Dose", "Frequency"], ["MTX", "7.5", "Weekly"]]
        assert detect_header_row(cells) is True

    def test_numeric_first_row_not_header(self) -> None:
        cells = [["1.0", "2.0", "3.0"], ["4.0", "5.0", "6.0"]]
        assert detect_header_row(cells) is False

    def test_single_row_not_header(self) -> None:
        cells = [["Drug", "Dose"]]
        assert detect_header_row(cells) is False

    def test_empty_cells_not_header(self) -> None:
        assert detect_header_row([]) is False

    def test_mixed_first_row_majority_text(self) -> None:
        cells = [["Drug", "Dose", "Note"], ["1.0", "2.0", "3.0"]]
        assert detect_header_row(cells) is True

# -----------------------------------------------------------------------
# cells_to_markdown
# -----------------------------------------------------------------------

class TestCellsToMarkdown:
    def test_basic_table(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        result = cells_to_markdown(cells)
        assert "| Drug | Dose |" in result
        assert "| MTX | 7.5mg |" in result
        assert "|---|---|" in result

    def test_table_with_title(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        result = cells_to_markdown(cells, table_title="Table 1: Dosing")
        assert "<!-- Table 1: Dosing -->" in result

    def test_no_header_generates_column_names(self) -> None:
        cells = [["1.0", "2.0"], ["3.0", "4.0"]]
        result = cells_to_markdown(cells)
        assert "Column 1" in result
        assert "Column 2" in result

    def test_single_column_bullet_list(self) -> None:
        cells = [["Item A"], ["Item B"], ["Item C"]]
        result = cells_to_markdown(cells)
        assert "- Item A" in result
        assert "- Item B" in result
        assert "|" not in result

    def test_single_column_with_title(self) -> None:
        cells = [["Item A"], ["Item B"]]
        result = cells_to_markdown(cells, table_title="Table 1")
        assert "<!-- Table 1 -->" in result
        assert "- Item A" in result

    def test_empty_cells_returns_empty(self) -> None:
        assert cells_to_markdown([]) == ""

    def test_pipe_in_cell_escaped(self) -> None:
        cells = [["A", "B"], ["x | y", "z"]]
        result = cells_to_markdown(cells)
        assert r"\|" in result

    def test_rows_padded_to_max_cols(self) -> None:
        cells = [["A", "B", "C"], ["X", "Y"]]
        result = cells_to_markdown(cells)
        assert result.count("|") > 0

    def test_empty_data_rows_returns_empty(self) -> None:
        # Only header, no data rows, no header detection (numeric)
        cells = [["1.0", "2.0"]]
        result = cells_to_markdown(cells)
        assert result == ""

# -----------------------------------------------------------------------
# find_table_caption
# -----------------------------------------------------------------------

class TestFindTableCaption:
    def test_caption_pattern_detected(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [
            make_block("Table 1: Dosing Schedule", bbox=[50.0, 255.0, 400.0, 275.0])
        ]
        result = find_table_caption(table_bbox, blocks)
        assert result == "Table 1: Dosing Schedule"

    def test_bold_block_above_detected(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [
            make_block("Monitoring Schedule", bbox=[50.0, 255.0, 400.0, 275.0], is_bold=True)
        ]
        result = find_table_caption(table_bbox, blocks)
        assert result == "Monitoring Schedule"

    def test_block_too_far_above_ignored(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [
            make_block("Table 1: Far Away", bbox=[50.0, 100.0, 400.0, 120.0])
        ]
        result = find_table_caption(table_bbox, blocks)
        assert result is None

    def test_block_below_table_ignored(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [
            make_block("Table 1: Below", bbox=[50.0, 510.0, 400.0, 530.0])
        ]
        result = find_table_caption(table_bbox, blocks)
        assert result is None

    def test_no_caption_returns_none(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [make_block("Normal text", bbox=[50.0, 255.0, 400.0, 275.0])]
        result = find_table_caption(table_bbox, blocks)
        assert result is None


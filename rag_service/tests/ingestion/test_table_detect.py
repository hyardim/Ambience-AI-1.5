from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

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
    finder = MagicMock()
    finder.tables = tables or []
    page.find_tables.return_value = finder
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

    def test_empty_first_row_not_header(self) -> None:
        cells = [[], ["Drug", "Dose"]]
        assert detect_header_row(cells) is False


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

    def test_all_empty_rows_returns_empty(self) -> None:
        cells = [[]]
        result = cells_to_markdown(cells)
        assert result == ""

    def test_pipe_in_cell_escaped(self) -> None:
        cells = [["A", "B"], ["x | y", "z"]]
        result = cells_to_markdown(cells)
        assert r"\|" in result

    def test_rows_padded_to_max_cols(self) -> None:
        cells = [["A", "B", "C"], ["X", "Y"]]
        result = cells_to_markdown(cells)
        assert result.count("|") > 0

    def test_all_empty_cells_returns_empty(self) -> None:
        cells = [["", ""], ["", ""]]
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
            make_block(
                "Monitoring Schedule", bbox=[50.0, 255.0, 400.0, 275.0], is_bold=True
            )
        ]
        result = find_table_caption(table_bbox, blocks)
        assert result == "Monitoring Schedule"

    def test_block_too_far_above_ignored(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [make_block("Table 1: Far Away", bbox=[50.0, 100.0, 400.0, 120.0])]
        result = find_table_caption(table_bbox, blocks)
        assert result is None

    def test_block_below_table_ignored(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [make_block("Table 1: Below", bbox=[50.0, 510.0, 400.0, 530.0])]
        result = find_table_caption(table_bbox, blocks)
        assert result is None

    def test_no_caption_returns_none(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [make_block("Normal text", bbox=[50.0, 255.0, 400.0, 275.0])]
        result = find_table_caption(table_bbox, blocks)
        assert result is None

    def test_closest_block_wins_when_multiple_candidates(self) -> None:
        table_bbox = [50.0, 300.0, 400.0, 500.0]
        blocks = [
            # Further away (40px above)
            make_block("Table 1: Far Caption", bbox=[50.0, 240.0, 400.0, 260.0]),
            # Closer (10px above)
            make_block("Table 2: Close Caption", bbox=[50.0, 280.0, 400.0, 290.0]),
        ]
        result = find_table_caption(table_bbox, blocks)
        assert result == "Table 2: Close Caption"


# -----------------------------------------------------------------------
# _is_pipe_table_block
# -----------------------------------------------------------------------


class TestIsPipeTableBlock:
    def test_pipe_table_detected(self) -> None:
        text = "| Drug | Dose | Freq |\n| MTX | 7.5 | Weekly |"
        assert _is_pipe_table_block(text) is True

    def test_single_pipe_line_not_table(self) -> None:
        text = "| Drug | Dose | Freq |"
        assert _is_pipe_table_block(text) is False

    def test_few_pipes_not_table(self) -> None:
        text = "a | b\nc | d"
        assert _is_pipe_table_block(text) is False

    def test_normal_text_not_table(self) -> None:
        assert _is_pipe_table_block("Normal paragraph text here.") is False

    def test_empty_string_not_table(self) -> None:
        assert _is_pipe_table_block("") is False


# -----------------------------------------------------------------------
# detect_tables_with_pymupdf
# -----------------------------------------------------------------------


class TestDetectTablesWithPymupdf:
    def test_basic_table_detected(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        fitz_table = make_fitz_table(cells)
        fitz_page = make_fitz_page(tables=[fitz_table])
        fitz_doc = make_fitz_doc(pages=[fitz_page], page_count=1)

        with patch("src.ingestion.table_detect.fitz.open", return_value=fitz_doc):
            result = detect_tables_with_pymupdf("test.pdf", page_num=1)

        assert len(result) == 1
        assert result[0]["cells"] == cells
        assert result[0]["page_number"] == 1

    def test_no_tables_returns_empty(self) -> None:
        fitz_page = make_fitz_page(tables=[])
        fitz_doc = make_fitz_doc(pages=[fitz_page], page_count=1)

        with patch("src.ingestion.table_detect.fitz.open", return_value=fitz_doc):
            result = detect_tables_with_pymupdf("test.pdf", page_num=1)

        assert result == []

    def test_page_out_of_range_returns_empty(self) -> None:
        fitz_doc = make_fitz_doc(page_count=1)

        with patch("src.ingestion.table_detect.fitz.open", return_value=fitz_doc):
            result = detect_tables_with_pymupdf("test.pdf", page_num=99)

        assert result == []

    def test_exception_returns_empty(self) -> None:
        with patch(
            "src.ingestion.table_detect.fitz.open",
            side_effect=Exception("file error"),
        ):
            result = detect_tables_with_pymupdf("missing.pdf", page_num=1)

        assert result == []


# -----------------------------------------------------------------------
# detect_and_convert_tables
# -----------------------------------------------------------------------


class TestDetectAndConvertTables:
    def test_returns_same_structure(self) -> None:
        doc = make_sectioned_doc()
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "test.pdf")
        assert "source_path" in result
        assert "pages" in result

    def test_all_blocks_tagged_with_content_type(self) -> None:
        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Text content", block_id=0),
                        make_block("Heading", block_id=1, is_heading=True),
                    ],
                )
            ]
        )
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "test.pdf")
        for page in result["pages"]:
            for block in page["blocks"]:
                assert "content_type" in block

    def test_heading_tagged_correctly(self) -> None:
        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Introduction", block_id=0, is_heading=True),
                    ],
                )
            ]
        )
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "test.pdf")
        assert result["pages"][0]["blocks"][0]["content_type"] == "heading"

    def test_text_tagged_correctly(self) -> None:
        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Body text", block_id=0),
                    ],
                )
            ]
        )
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "test.pdf")
        assert result["pages"][0]["blocks"][0]["content_type"] == "text"

    def test_table_chunk_inserted(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        table_bbox = [50.0, 200.0, 400.0, 350.0]
        table_info = [{"cells": cells, "bbox": table_bbox, "page_number": 1}]

        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block(
                            "Text", block_id=0, bbox=[50.0, 210.0, 400.0, 230.0]
                        ),
                    ],
                )
            ]
        )

        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf",
            return_value=table_info,
        ):
            result = detect_and_convert_tables(doc, "test.pdf")

        table_blocks = [
            b for b in result["pages"][0]["blocks"] if b.get("content_type") == "table"
        ]
        assert len(table_blocks) == 1
        assert "Drug" in table_blocks[0]["text"]

    def test_table_chunk_has_required_fields(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        table_bbox = [50.0, 200.0, 400.0, 350.0]
        table_info = [{"cells": cells, "bbox": table_bbox, "page_number": 1}]

        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block(
                            "Text", block_id=0, bbox=[50.0, 210.0, 400.0, 230.0]
                        ),
                    ],
                )
            ]
        )

        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf",
            return_value=table_info,
        ):
            result = detect_and_convert_tables(doc, "test.pdf")

        table_block = next(
            b for b in result["pages"][0]["blocks"] if b.get("content_type") == "table"
        )
        assert all(
            k in table_block
            for k in [
                "content_type",
                "text",
                "table_title",
                "section_path",
                "section_title",
                "page_number",
                "bbox",
                "include_in_chunks",
            ]
        )
        assert table_block["include_in_chunks"] is True

    def test_caption_detected_and_stored(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        table_bbox = [50.0, 200.0, 400.0, 350.0]
        table_info = [{"cells": cells, "bbox": table_bbox, "page_number": 1}]

        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block(
                            "Table 1: Dosing",
                            block_id=0,
                            bbox=[50.0, 155.0, 400.0, 175.0],
                        ),
                        make_block(
                            "Content", block_id=1, bbox=[50.0, 210.0, 400.0, 230.0]
                        ),
                    ],
                )
            ]
        )

        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf",
            return_value=table_info,
        ):
            result = detect_and_convert_tables(doc, "test.pdf")

        table_block = next(
            b for b in result["pages"][0]["blocks"] if b.get("content_type") == "table"
        )
        assert table_block["table_title"] == "Table 1: Dosing"

    def test_empty_markdown_table_skipped(self) -> None:
        # cells_to_markdown returns "" for header-only table (text header, no data rows)
        # detect_header_row requires len >= 2, so single row → not header → data row
        # Use empty cells list instead
        table_bbox = [50.0, 200.0, 400.0, 350.0]
        table_info = [{"cells": [], "bbox": table_bbox, "page_number": 1}]

        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block(
                            "Text", block_id=0, bbox=[50.0, 210.0, 400.0, 230.0]
                        ),
                    ],
                )
            ]
        )

        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf",
            return_value=table_info,
        ):
            result = detect_and_convert_tables(doc, "test.pdf")

        table_blocks = [
            b for b in result["pages"][0]["blocks"] if b.get("content_type") == "table"
        ]
        assert len(table_blocks) == 0

    def test_pipe_table_detected_by_heuristic(self) -> None:
        pipe_text = (
            "| Drug | Dose | Freq |\n| MTX | 7.5 | Weekly |\n| LEF | 20mg | Daily |"
        )
        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block(pipe_text, block_id=0),
                    ],
                )
            ]
        )
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "test.pdf")
        block = result["pages"][0]["blocks"][0]
        assert block["content_type"] == "table"
        assert block["include_in_chunks"] is True
        assert block["table_title"] is None
        assert block["page_number"] == 1

    def test_no_overlapping_blocks_table_skipped(self) -> None:
        cells = [["Drug", "Dose"], ["MTX", "7.5mg"]]
        table_bbox = [600.0, 600.0, 800.0, 800.0]
        table_info = [{"cells": cells, "bbox": table_bbox, "page_number": 1}]

        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Text", block_id=0, bbox=[10.0, 10.0, 100.0, 30.0]),
                    ],
                )
            ]
        )

        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf",
            return_value=table_info,
        ):
            result = detect_and_convert_tables(doc, "test.pdf")

        table_blocks = [
            b for b in result["pages"][0]["blocks"] if b.get("content_type") == "table"
        ]
        assert len(table_blocks) == 0

    def test_source_path_preserved(self) -> None:
        doc = make_sectioned_doc(source_path="guidelines.pdf")
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "guidelines.pdf")
        assert result["source_path"] == "guidelines.pdf"

    def test_empty_document(self) -> None:
        doc = make_sectioned_doc(pages=[])
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result = detect_and_convert_tables(doc, "test.pdf")
        assert result["pages"] == []

    def test_deterministic(self) -> None:
        doc = make_sectioned_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Body text", block_id=0),
                    ],
                )
            ]
        )
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result1 = detect_and_convert_tables(doc, "test.pdf")
        with patch(
            "src.ingestion.table_detect.detect_tables_with_pymupdf", return_value=[]
        ):
            result2 = detect_and_convert_tables(doc, "test.pdf")
        assert result1 == result2

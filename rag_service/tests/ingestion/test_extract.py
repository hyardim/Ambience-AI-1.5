from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.extract import (
    PDFExtractionError,
    _detect_columns,
    _detect_needs_ocr,
    _extract_page,
    _extract_text_block,
    _sort_blocks,
    extract_raw_document,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_span(
    text: str = "Hello",
    size: float = 12.0,
    font: str = "Arial",
    flags: int = 0,
) -> dict[str, Any]:
    return {"text": text, "size": size, "font": font, "flags": flags}


def make_block(
    spans: list[dict] | None = None,
    bbox: tuple = (0, 0, 100, 20),
    block_type: int = 0,
) -> dict[str, Any]:
    if spans is None:
        spans = [make_span()]
    return {
        "type": block_type,
        "bbox": bbox,
        "lines": [{"spans": spans}],
    }


def make_fitz_page(
    blocks: list[dict] | None = None,
    width: float = 595.0,
) -> MagicMock:
    page = MagicMock()
    page.rect.width = width
    if blocks is None:
        blocks = [make_block()]
    page.get_text.return_value = {"blocks": blocks}
    return page


def make_fitz_doc(pages: list[MagicMock] | None = None) -> MagicMock:
    doc = MagicMock()
    if pages is None:
        pages = [make_fitz_page()]
    doc.page_count = len(pages)
    doc.__iter__ = MagicMock(return_value=iter(enumerate(pages, start=1)))
    doc.__enter__ = MagicMock(return_value=doc)
    doc.__exit__ = MagicMock(return_value=False)
    return doc


# -----------------------------------------------------------------------
# _detect_columns
# -----------------------------------------------------------------------


class TestDetectColumns:
    def test_single_column(self) -> None:
        blocks = [
            {"bbox": [10, 0, 200, 20]},
            {"bbox": [10, 30, 200, 50]},
            {"bbox": [10, 60, 200, 80]},
        ]
        assert _detect_columns(blocks, page_width=595.0) == 1

    def test_two_columns(self) -> None:
        blocks = [
            {"bbox": [10, 0, 200, 20]},
            {"bbox": [10, 30, 200, 50]},
            {"bbox": [310, 0, 500, 20]},
            {"bbox": [310, 30, 500, 50]},
        ]
        assert _detect_columns(blocks, page_width=595.0) == 2

    def test_one_block_each_side_not_two_columns(self) -> None:
        blocks = [
            {"bbox": [10, 0, 200, 20]},
            {"bbox": [310, 0, 500, 20]},
        ]
        assert _detect_columns(blocks, page_width=595.0) == 1

    def test_empty_blocks(self) -> None:
        assert _detect_columns([], page_width=595.0) == 1


# -----------------------------------------------------------------------
# _sort_blocks
# -----------------------------------------------------------------------


class TestSortBlocks:
    def test_single_column_top_to_bottom(self) -> None:
        blocks = [
            {"bbox": [10, 100, 200, 120]},
            {"bbox": [10, 20, 200, 40]},
            {"bbox": [10, 60, 200, 80]},
        ]
        sorted_b = _sort_blocks(blocks, page_width=595.0)
        y_positions = [b["bbox"][1] for b in sorted_b]
        assert y_positions == sorted(y_positions)

    def test_two_column_left_before_right(self) -> None:
        blocks = [
            {"bbox": [310, 10, 500, 30]},
            {"bbox": [10, 10, 200, 30]},
            {"bbox": [310, 50, 500, 70]},
            {"bbox": [10, 50, 200, 70]},
        ]
        sorted_b = _sort_blocks(blocks, page_width=595.0)
        assert sorted_b[0]["bbox"][0] == 10
        assert sorted_b[1]["bbox"][0] == 10
        assert sorted_b[2]["bbox"][0] == 310
        assert sorted_b[3]["bbox"][0] == 310

    def test_left_to_right_same_row(self) -> None:
        blocks = [
            {"bbox": [300, 10, 500, 30]},
            {"bbox": [10, 10, 200, 30]},
        ]
        sorted_b = _sort_blocks(blocks, page_width=595.0)
        assert sorted_b[0]["bbox"][0] == 10


# -----------------------------------------------------------------------
# _extract_text_block
# -----------------------------------------------------------------------


class TestExtractTextBlock:
    def test_basic_extraction(self) -> None:
        block = make_block(spans=[make_span("Hello world", size=12.0, font="Arial")])
        result = _extract_text_block(block)
        assert result is not None
        assert result["text"] == "Hello world"
        assert result["font_size"] == 12.0
        assert result["font_name"] == "Arial"
        assert result["is_bold"] is False

    def test_bold_detection(self) -> None:
        block = make_block(spans=[make_span("Bold", flags=16)])
        result = _extract_text_block(block)
        assert result is not None
        assert result["is_bold"] is True

    def test_not_bold_when_minority(self) -> None:
        block = make_block(
            spans=[
                make_span("Normal", flags=0),
                make_span("Normal", flags=0),
                make_span("Bold", flags=16),
            ]
        )
        result = _extract_text_block(block)
        assert result is not None
        assert result["is_bold"] is False

    def test_empty_text_returns_none(self) -> None:
        block = make_block(spans=[make_span("   ")])
        result = _extract_text_block(block)
        assert result is None

    def test_no_lines_returns_none(self) -> None:
        block = {"type": 0, "bbox": (0, 0, 100, 20), "lines": []}
        result = _extract_text_block(block)
        assert result is None

    def test_missing_font_metadata_uses_defaults(self) -> None:
        block = {
            "type": 0,
            "bbox": (0, 0, 100, 20),
            "lines": [{"spans": [{"text": "Hello"}]}],
        }
        result = _extract_text_block(block)
        assert result is not None
        assert result["font_size"] == 0.0
        assert result["font_name"] == ""
        assert result["is_bold"] is False

    def test_dominant_font_selected(self) -> None:
        block = make_block(
            spans=[
                make_span("a", font="Arial"),
                make_span("b", font="Arial"),
                make_span("c", font="Times"),
            ]
        )
        result = _extract_text_block(block)
        assert result is not None
        assert result["font_name"] == "Arial"

    def test_average_font_size(self) -> None:
        block = make_block(
            spans=[
                make_span("a", size=10.0),
                make_span("b", size=20.0),
            ]
        )
        result = _extract_text_block(block)
        assert result is not None
        assert result["font_size"] == 15.0

    def test_bbox_preserved(self) -> None:
        block = make_block(bbox=(10, 20, 300, 40))
        result = _extract_text_block(block)
        assert result is not None
        assert result["bbox"] == [10, 20, 300, 40]

    def test_multiline_preserved(self) -> None:
        block = {
            "type": 0,
            "bbox": (0, 0, 100, 50),
            "lines": [
                {"spans": [make_span("Line one")]},
                {"spans": [make_span("Line two")]},
            ],
        }
        result = _extract_text_block(block)
        assert result is not None
        assert "Line one" in result["text"]
        assert "Line two" in result["text"]

    def test_malformed_block_returns_none(self) -> None:
        result = _extract_text_block({"type": 0, "bbox": None, "lines": None})
        assert result is None


# -----------------------------------------------------------------------
# _detect_needs_ocr
# -----------------------------------------------------------------------


class TestDetectNeedsOcr:
    def test_low_text_density_is_ocr(self) -> None:
        pages = [{"blocks": [{"text": "Hi"}]}]
        assert _detect_needs_ocr(pages, num_pages=1) is True

    def test_high_text_density_not_ocr(self) -> None:
        long_text = "word " * 200
        pages = [{"blocks": [{"text": long_text}]}]
        assert _detect_needs_ocr(pages, num_pages=1) is False

    def test_zero_pages_not_ocr(self) -> None:
        assert _detect_needs_ocr([], num_pages=0) is False

    def test_empty_pages_is_ocr(self) -> None:
        pages = [{"blocks": []}]
        assert _detect_needs_ocr(pages, num_pages=1) is True


# -----------------------------------------------------------------------
# _extract_page
# -----------------------------------------------------------------------


class TestExtractPage:
    def test_page_number_preserved(self) -> None:
        page = make_fitz_page()
        result = _extract_page(page, 3)
        assert result["page_number"] == 3

    def test_image_blocks_ignored(self) -> None:
        page = make_fitz_page(
            blocks=[
                make_block(block_type=1),
                make_block(spans=[make_span("Text")], block_type=0),
            ]
        )
        result = _extract_page(page, 1)
        assert len(result["blocks"]) == 1
        assert result["blocks"][0]["text"] == "Text"

    def test_block_ids_sequential(self) -> None:
        page = make_fitz_page(
            blocks=[
                make_block(spans=[make_span("A")], bbox=(10, 10, 200, 30)),
                make_block(spans=[make_span("B")], bbox=(10, 50, 200, 70)),
                make_block(spans=[make_span("C")], bbox=(10, 90, 200, 110)),
            ]
        )
        result = _extract_page(page, 1)
        ids = [b["block_id"] for b in result["blocks"]]
        assert ids == list(range(len(ids)))

    def test_all_block_fields_present(self) -> None:
        page = make_fitz_page()
        result = _extract_page(page, 1)
        block = result["blocks"][0]
        assert all(
            k in block
            for k in ["block_id", "text", "bbox", "font_size", "font_name", "is_bold"]
        )


# -----------------------------------------------------------------------
# extract_raw_document
# -----------------------------------------------------------------------


class TestExtractRawDocument:
    def test_basic_extraction(self) -> None:
        doc = make_fitz_doc()
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("test.pdf")
        assert result["num_pages"] == 1
        assert len(result["pages"]) == 1

    def test_source_path_preserved(self) -> None:
        doc = make_fitz_doc()
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("data/test.pdf")
        assert result["source_path"] == "data/test.pdf"

    def test_path_object_accepted(self) -> None:
        doc = make_fitz_doc()
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document(Path("data/test.pdf"))
        assert result["source_path"] == "data/test.pdf"

    def test_empty_pdf_returns_valid_structure(self) -> None:
        doc = make_fitz_doc(pages=[])
        doc.page_count = 0
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("empty.pdf")
        assert result["num_pages"] == 0
        assert result["pages"] == []
        assert result["needs_ocr"] is False

    def test_corrupted_pdf_raises_error(self) -> None:
        with patch(
            "src.ingestion.extract.fitz.open",
            side_effect=Exception("corrupted"),
        ):
            with pytest.raises(PDFExtractionError, match="Failed to open PDF"):
                extract_raw_document("corrupted.pdf")

    def test_file_not_found_raises_error(self) -> None:
        with patch(
            "src.ingestion.extract._open_pdf",
            side_effect=PDFExtractionError("PDF file not found: missing.pdf"),
        ):
            with pytest.raises(PDFExtractionError, match="PDF file not found"):
                extract_raw_document("missing.pdf")

    def test_bad_page_skipped_not_crash(self) -> None:
        good_page = make_fitz_page()
        bad_page = MagicMock()
        bad_page.rect.width = 595.0
        bad_page.get_text.side_effect = Exception("page error")

        doc = MagicMock()
        doc.page_count = 2
        doc.__iter__ = MagicMock(return_value=iter([(1, bad_page), (2, good_page)]))
        doc.__enter__ = MagicMock(return_value=doc)
        doc.__exit__ = MagicMock(return_value=False)

        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("test.pdf")

        assert len(result["pages"]) == 1
        assert result["pages"][0]["page_number"] == 2

    def test_page_numbers_one_indexed(self) -> None:
        doc = make_fitz_doc(pages=[make_fitz_page(), make_fitz_page()])
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("test.pdf")
        assert [p["page_number"] for p in result["pages"]] == [1, 2]

    def test_needs_ocr_true_for_scanned(self) -> None:
        page = make_fitz_page(blocks=[make_block(spans=[make_span("Hi")])])
        doc = make_fitz_doc(pages=[page])
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("scanned.pdf")
        assert result["needs_ocr"] is True

    def test_needs_ocr_false_for_normal(self) -> None:
        long_text = "medical guidelines content " * 20
        page = make_fitz_page(blocks=[make_block(spans=[make_span(long_text)])])
        doc = make_fitz_doc(pages=[page])
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("normal.pdf")
        assert result["needs_ocr"] is False

    def test_deterministic_output(self) -> None:
        page = make_fitz_page(
            blocks=[
                make_block(spans=[make_span("A")], bbox=(10, 10, 200, 30)),
                make_block(spans=[make_span("B")], bbox=(10, 50, 200, 70)),
            ]
        )
        doc1 = make_fitz_doc(pages=[page])
        doc2 = make_fitz_doc(pages=[page])

        with patch("src.ingestion.extract.fitz.open", return_value=doc1):
            result1 = extract_raw_document("test.pdf")
        with patch("src.ingestion.extract.fitz.open", return_value=doc2):
            result2 = extract_raw_document("test.pdf")

        assert result1 == result2

    def test_all_required_fields_present(self) -> None:
        doc = make_fitz_doc()
        with patch("src.ingestion.extract.fitz.open", return_value=doc):
            result = extract_raw_document("test.pdf")

        required_fields = ["source_path", "num_pages", "needs_ocr", "pages"]
        assert all(k in result for k in required_fields)
        block = result["pages"][0]["blocks"][0]
        assert all(
            k in block
            for k in ["block_id", "text", "bbox", "font_size", "font_name", "is_bold"]
        )

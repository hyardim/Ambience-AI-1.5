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

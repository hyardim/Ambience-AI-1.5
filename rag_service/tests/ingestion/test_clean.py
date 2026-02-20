from __future__ import annotations

from typing import Any

from src.ingestion.clean import (
    _fix_hyphenated_line_breaks,
    _is_header_footer_block,
    _normalize_bullets_and_lists,
    _normalize_unicode,
    _normalize_whitespace,
    _remove_duplicate_pages,
    _remove_repeated_headers_footers,
    clean_document,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def make_block(
    text: str,
    block_id: int = 0,
    bbox: list[float] | None = None,
) -> dict[str, Any]:
    if bbox is None:
        bbox = [10.0, 400.0, 500.0, 420.0]  # middle of page by default
    return {
        "block_id": block_id,
        "text": text,
        "bbox": bbox,
        "font_size": 12.0,
        "font_name": "Arial",
        "is_bold": False,
    }


def make_page(
    page_number: int,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if blocks is None:
        blocks = [make_block("Some content here.")]
    return {"page_number": page_number, "blocks": blocks}


def make_raw_doc(
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if pages is None:
        pages = [make_page(1)]
    return {
        "source_path": "test.pdf",
        "num_pages": len(pages),
        "needs_ocr": False,
        "pages": pages,
    }

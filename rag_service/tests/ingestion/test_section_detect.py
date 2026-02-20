from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.section_detect import (
    _compute_page_median_font_size,
    _detect_heading,
    add_section_metadata,
    is_allcaps_heading,
    is_bold_heading,
    is_excluded_section,
    is_fontsize_heading,
    is_numbered_heading,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def make_block(
    text: str,
    block_id: int = 0,
    is_bold: bool = False,
    font_size: float = 12.0,
    bbox: list[float] | None = None,
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "text": text,
        "bbox": bbox or [10.0, 400.0, 500.0, 420.0],
        "font_size": font_size,
        "font_name": "Arial",
        "is_bold": is_bold,
    }


def make_page(
    page_number: int,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if blocks is None:
        blocks = [make_block("Some content here.")]
    return {"page_number": page_number, "blocks": blocks}


def make_clean_doc(
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


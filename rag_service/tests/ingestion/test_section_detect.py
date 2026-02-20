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

# -----------------------------------------------------------------------
# is_numbered_heading
# -----------------------------------------------------------------------

class TestIsNumberedHeading:
    def test_level_1_heading(self) -> None:
        match, level, clean = is_numbered_heading("1 Introduction")
        assert match is True
        assert level == 1
        assert clean == "Introduction"

    def test_level_2_heading(self) -> None:
        match, level, clean = is_numbered_heading("2.1 Monitoring")
        assert match is True
        assert level == 2
        assert clean == "Monitoring"

    def test_level_3_heading(self) -> None:
        match, level, clean = is_numbered_heading("3.2.1 Blood Tests")
        assert match is True
        assert level == 3
        assert clean == "Blood Tests"

    def test_trailing_dot_accepted(self) -> None:
        match, level, clean = is_numbered_heading("2.1. Monitoring")
        assert match is True
        assert level == 2
        assert clean == "Monitoring"

    def test_dosage_not_heading(self) -> None:
        match, level, clean = is_numbered_heading("2.5 mg dose")
        assert match is False

    def test_lowercase_after_number_not_heading(self) -> None:
        match, level, _ = is_numbered_heading("1 tablet daily")
        assert match is False

    def test_short_text_not_heading(self) -> None:
        match, _, _ = is_numbered_heading("1 Ab")
        assert match is False

    def test_no_number_not_heading(self) -> None:
        match, _, _ = is_numbered_heading("Introduction")
        assert match is False

    def test_empty_string(self) -> None:
        match, _, _ = is_numbered_heading("")
        assert match is False

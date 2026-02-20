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

# -----------------------------------------------------------------------
# _normalize_unicode
# -----------------------------------------------------------------------

class TestNormalizeUnicode:
    def test_ligature_fi_normalized(self) -> None:
        assert _normalize_unicode("ﬁle") == "file"

    def test_ligature_fl_normalized(self) -> None:
        assert _normalize_unicode("ﬂow") == "flow"

    def test_normal_text_unchanged(self) -> None:
        assert _normalize_unicode("hello world") == "hello world"

    def test_empty_string(self) -> None:
        assert _normalize_unicode("") == ""

    def test_medical_symbols_preserved(self) -> None:
        text = "≥ 10 mg/dl"
        result = _normalize_unicode(text)
        assert "≥" in result

# -----------------------------------------------------------------------
# _normalize_whitespace
# -----------------------------------------------------------------------

class TestNormalizeWhitespace:
    def test_multiple_spaces_collapsed(self) -> None:
        assert _normalize_whitespace("hello   world") == "hello world"

    def test_crlf_normalized(self) -> None:
        assert _normalize_whitespace("line1\r\nline2") == "line1\nline2"

    def test_three_newlines_collapsed_to_two(self) -> None:
        assert _normalize_whitespace("a\n\n\nb") == "a\n\nb"

    def test_four_newlines_collapsed_to_two(self) -> None:
        assert _normalize_whitespace("a\n\n\n\nb") == "a\n\nb"

    def test_single_newline_preserved(self) -> None:
        assert _normalize_whitespace("a\nb") == "a\nb"

    def test_leading_trailing_whitespace_trimmed(self) -> None:
        assert _normalize_whitespace("  hello  ") == "hello"

    def test_empty_string(self) -> None:
        assert _normalize_whitespace("") == ""

    def test_two_newlines_preserved(self) -> None:
        assert _normalize_whitespace("a\n\nb") == "a\n\nb"


# -----------------------------------------------------------------------
# _fix_hyphenated_line_breaks
# -----------------------------------------------------------------------

class TestFixHyphenatedLineBreaks:
    def test_basic_hyphen_merged(self) -> None:
        assert _fix_hyphenated_line_breaks("treat-\nment") == "treatment"

    def test_medical_term_merged(self) -> None:
        assert _fix_hyphenated_line_breaks("inflam-\nmation") == "inflammation"

    def test_covid_preserved(self) -> None:
        assert _fix_hyphenated_line_breaks("COVID-19") == "COVID-19"

    def test_uppercase_next_line_not_merged(self) -> None:
        result = _fix_hyphenated_line_breaks("anti-\nInflammatory")
        assert result == "anti-\nInflammatory"

    def test_number_after_hyphen_not_merged(self) -> None:
        assert _fix_hyphenated_line_breaks("step-\n1") == "step-\n1"

    def test_multiple_hyphens_in_text(self) -> None:
        text = "treat-\nment and anti-\ncoagulation"
        result = _fix_hyphenated_line_breaks(text)
        assert result == "treatment and anticoagulation"

    def test_no_hyphen_unchanged(self) -> None:
        assert _fix_hyphenated_line_breaks("hello world") == "hello world"

    def test_empty_string(self) -> None:
        assert _fix_hyphenated_line_breaks("") == ""

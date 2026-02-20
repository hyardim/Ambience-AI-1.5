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

# -----------------------------------------------------------------------
# _normalize_bullets_and_lists
# -----------------------------------------------------------------------

class TestNormalizeBulletsAndLists:
    def test_bullet_dot_normalized(self) -> None:
        assert _normalize_bullets_and_lists("• item") == "- item"

    def test_bullet_circle_normalized(self) -> None:
        assert _normalize_bullets_and_lists("◦ item") == "- item"

    def test_bullet_square_normalized(self) -> None:
        assert _normalize_bullets_and_lists("▪ item") == "- item"

    def test_bullet_arrow_normalized(self) -> None:
        assert _normalize_bullets_and_lists("▸ item") == "- item"

    def test_bullet_check_normalized(self) -> None:
        assert _normalize_bullets_and_lists("✓ item") == "- item"

    def test_bullet_dash_normalized(self) -> None:
        assert _normalize_bullets_and_lists("– item") == "- item"

    def test_numbered_paren_normalized(self) -> None:
        assert _normalize_bullets_and_lists("1) item") == "1. item"

    def test_numbered_bracket_normalized(self) -> None:
        assert _normalize_bullets_and_lists("(1) item") == "1. item"

    def test_lettered_paren_normalized(self) -> None:
        assert _normalize_bullets_and_lists("a) item") == "a. item"

    def test_lettered_bracket_normalized(self) -> None:
        assert _normalize_bullets_and_lists("(a) item") == "a. item"

    def test_multiline_bullets(self) -> None:
        text = "• item one\n• item two"
        result = _normalize_bullets_and_lists(text)
        assert result == "- item one\n- item two"

    def test_non_bullet_unchanged(self) -> None:
        assert _normalize_bullets_and_lists("normal text") == "normal text"

    def test_empty_string(self) -> None:
        assert _normalize_bullets_and_lists("") == ""

# -----------------------------------------------------------------------
# _remove_repeated_headers_footers
# -----------------------------------------------------------------------

class TestRemoveRepeatedHeadersFooters:
    def test_repeated_header_removed(self) -> None:
        # Block in header position (y0 < 842 * 0.15 = 126)
        header_block = make_block("BSR Guidelines", bbox=[10.0, 20.0, 500.0, 40.0])
        pages = [
            make_page(i, blocks=[
                header_block.copy(),
                make_block(f"Content page {i}", block_id=1),
            ])
            for i in range(1, 6)
        ]
        cleaned, removed = _remove_repeated_headers_footers(pages, num_pages=5)
        assert removed == 5
        for page in cleaned:
            texts = [b["text"] for b in page["blocks"]]
            assert "BSR Guidelines" not in texts

    def test_repeated_footer_removed(self) -> None:
        # Block in footer position (y3 > 842 * 0.85 = 715)
        footer_block = make_block("Page 1", bbox=[10.0, 750.0, 500.0, 770.0])
        pages = [
            make_page(i, blocks=[
                make_block(f"Content {i}", block_id=0),
                footer_block.copy(),
            ])
            for i in range(1, 6)
        ]
        cleaned, removed = _remove_repeated_headers_footers(pages, num_pages=5)
        assert removed == 5

    def test_non_repeated_block_kept(self) -> None:
        # Block in header position but only on 1 of 5 pages (20% < 60%)
        pages = [make_page(i) for i in range(1, 6)]
        pages[0]["blocks"].append(
            make_block("Unique header", bbox=[10.0, 20.0, 500.0, 40.0])
        )
        cleaned, removed = _remove_repeated_headers_footers(pages, num_pages=5)
        assert removed == 0

    def test_middle_block_not_removed(self) -> None:
        # Block in middle of page — should never be removed
        middle_block = make_block("Same text every page", bbox=[10.0, 400.0, 500.0, 420.0])
        pages = [
            make_page(i, blocks=[middle_block.copy()])
            for i in range(1, 6)
        ]
        cleaned, removed = _remove_repeated_headers_footers(pages, num_pages=5)
        assert removed == 0

    def test_empty_pages_returns_zero_removed(self) -> None:
        cleaned, removed = _remove_repeated_headers_footers([], num_pages=0)
        assert removed == 0
        assert cleaned == []

# -----------------------------------------------------------------------
# _is_header_footer_block
# -----------------------------------------------------------------------

class TestIsHeaderFooterBlock:
    def test_matching_pattern_returns_true(self) -> None:
        block = make_block("bsr guidelines", bbox=[10.0, 20.0, 500.0, 40.0])
        patterns = {("bsr guidelines", 20)}
        assert _is_header_footer_block(block, patterns) is True

    def test_non_matching_pattern_returns_false(self) -> None:
        block = make_block("some content", bbox=[10.0, 400.0, 500.0, 420.0])
        patterns = {("bsr guidelines", 20)}
        assert _is_header_footer_block(block, patterns) is False

    def test_empty_patterns_returns_false(self) -> None:
        block = make_block("any text")
        assert _is_header_footer_block(block, set()) is False


# -----------------------------------------------------------------------
# _remove_duplicate_pages
# -----------------------------------------------------------------------

class TestRemoveDuplicatePages:
    def test_duplicate_page_removed(self) -> None:
        page1 = make_page(1, blocks=[make_block("Same content")])
        page2 = make_page(2, blocks=[make_block("Same content")])
        unique, removed = _remove_duplicate_pages([page1, page2])
        assert removed == 1
        assert len(unique) == 1
        assert unique[0]["page_number"] == 1

    def test_unique_pages_kept(self) -> None:
        pages = [
            make_page(1, blocks=[make_block("Content A")]),
            make_page(2, blocks=[make_block("Content B")]),
            make_page(3, blocks=[make_block("Content C")]),
        ]
        unique, removed = _remove_duplicate_pages(pages)
        assert removed == 0
        assert len(unique) == 3

    def test_three_duplicates_keeps_first(self) -> None:
        pages = [make_page(i, blocks=[make_block("Same")]) for i in range(1, 4)]
        unique, removed = _remove_duplicate_pages(pages)
        assert removed == 2
        assert unique[0]["page_number"] == 1

    def test_empty_pages(self) -> None:
        unique, removed = _remove_duplicate_pages([])
        assert removed == 0
        assert unique == []

    def test_slightly_different_pages_kept(self) -> None:
        page1 = make_page(1, blocks=[make_block("Content A")])
        page2 = make_page(2, blocks=[make_block("Content B")])
        unique, removed = _remove_duplicate_pages([page1, page2])
        assert removed == 0

# -----------------------------------------------------------------------
# clean_document
# -----------------------------------------------------------------------

class TestCleanDocument:
    def test_returns_same_structure(self) -> None:
        raw_doc = make_raw_doc()
        result = clean_document(raw_doc)
        assert "source_path" in result
        assert "num_pages" in result
        assert "needs_ocr" in result
        assert "pages" in result

    def test_source_path_preserved(self) -> None:
        raw_doc = make_raw_doc()
        result = clean_document(raw_doc)
        assert result["source_path"] == "test.pdf"

    def test_unicode_normalized(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("ﬁle and ﬂow")])
        ])
        result = clean_document(raw_doc)
        assert result["pages"][0]["blocks"][0]["text"] == "file and flow"

    def test_whitespace_normalized(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("hello   world")])
        ])
        result = clean_document(raw_doc)
        assert result["pages"][0]["blocks"][0]["text"] == "hello world"

    def test_hyphenated_line_break_merged(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("treat-\nment")])
        ])
        result = clean_document(raw_doc)
        assert result["pages"][0]["blocks"][0]["text"] == "treatment"

    def test_bullets_normalized(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("• item one\n• item two")])
        ])
        result = clean_document(raw_doc)
        assert result["pages"][0]["blocks"][0]["text"] == "- item one\n- item two"

    def test_empty_blocks_removed(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[
                make_block("Real content", block_id=0),
                make_block("   ", block_id=1),
            ])
        ])
        result = clean_document(raw_doc)
        assert len(result["pages"][0]["blocks"]) == 1
        assert result["pages"][0]["blocks"][0]["text"] == "Real content"

    def test_bbox_preserved(self) -> None:
        bbox = [10.0, 200.0, 500.0, 220.0]
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("Content", bbox=bbox)])
        ])
        result = clean_document(raw_doc)
        assert result["pages"][0]["blocks"][0]["bbox"] == bbox

    def test_block_order_preserved(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[
                make_block("First", block_id=0),
                make_block("Second", block_id=1),
                make_block("Third", block_id=2),
            ])
        ])
        result = clean_document(raw_doc)
        texts = [b["text"] for b in result["pages"][0]["blocks"]]
        assert texts == ["First", "Second", "Third"]

    def test_duplicate_pages_removed(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("Same content")]),
            make_page(2, blocks=[make_block("Same content")]),
            make_page(3, blocks=[make_block("Different content")]),
        ])
        result = clean_document(raw_doc)
        assert len(result["pages"]) == 2

    def test_repeated_headers_removed(self) -> None:
        header = make_block("BSR Guidelines", bbox=[10.0, 20.0, 500.0, 40.0])
        pages = [
            make_page(i, blocks=[
                {**header, "block_id": 0},
                make_block(f"Content {i}", block_id=1),
            ])
            for i in range(1, 6)
        ]
        raw_doc = make_raw_doc(pages=pages)
        result = clean_document(raw_doc)
        for page in result["pages"]:
            texts = [b["text"] for b in page["blocks"]]
            assert "BSR Guidelines" not in texts

    def test_deterministic(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("ﬁle treat-\nment • item")])
        ])
        result1 = clean_document(raw_doc)
        result2 = clean_document(raw_doc)
        assert result1 == result2

    def test_empty_document(self) -> None:
        raw_doc = make_raw_doc(pages=[])
        result = clean_document(raw_doc)
        assert result["pages"] == []

    def test_covid_hyphen_preserved(self) -> None:
        raw_doc = make_raw_doc(pages=[
            make_page(1, blocks=[make_block("COVID-19 patients")])
        ])
        result = clean_document(raw_doc)
        assert "COVID-19" in result["pages"][0]["blocks"][0]["text"]
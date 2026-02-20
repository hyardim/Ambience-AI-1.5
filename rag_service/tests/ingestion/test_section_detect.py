from __future__ import annotations

from typing import Any

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

    def test_hyphenated_heading(self) -> None:
        match, level, clean = is_numbered_heading("1 COVID-19 Guidelines")
        assert match is True
        assert clean == "COVID-19 Guidelines"

    def test_heading_with_colon(self) -> None:
        match, level, clean = is_numbered_heading("3 Section A: Overview")
        assert match is True
        assert clean == "Section A: Overview"

    def test_postoperative_heading(self) -> None:
        match, level, clean = is_numbered_heading("2.1 Post-operative Care")
        assert match is True
        assert clean == "Post-operative Care"


# -----------------------------------------------------------------------
# is_allcaps_heading
# -----------------------------------------------------------------------


class TestIsAllcapsHeading:
    def test_basic_allcaps(self) -> None:
        assert is_allcaps_heading("INTRODUCTION") is True

    def test_multiword_allcaps(self) -> None:
        assert is_allcaps_heading("LABORATORY PROCEDURES") is True

    def test_too_many_words(self) -> None:
        assert (
            is_allcaps_heading("ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN")
            is False
        )

    def test_too_long(self) -> None:
        assert is_allcaps_heading("A" * 81) is False

    def test_starts_with_bullet(self) -> None:
        assert is_allcaps_heading("- IMPORTANT NOTE") is False

    def test_mixed_case_not_allcaps(self) -> None:
        assert is_allcaps_heading("Introduction") is False

    def test_empty_string(self) -> None:
        assert is_allcaps_heading("") is False

    def test_allcaps_with_numbers(self) -> None:
        # Numbers are non-alpha so only alpha chars checked
        assert is_allcaps_heading("COVID-19") is True

    def test_no_alpha_chars(self) -> None:
        assert is_allcaps_heading("!!! ???") is False


# -----------------------------------------------------------------------
# is_bold_heading
# -----------------------------------------------------------------------


class TestIsBoldHeading:
    def test_bold_short_text(self) -> None:
        block = make_block("Clinical Presentation", is_bold=True)
        assert is_bold_heading(block) is True

    def test_not_bold(self) -> None:
        block = make_block("Clinical Presentation", is_bold=False)
        assert is_bold_heading(block) is False

    def test_too_long(self) -> None:
        block = make_block("A" * 101, is_bold=True)
        assert is_bold_heading(block) is False

    def test_too_many_words(self) -> None:
        text = "word " * 15
        block = make_block(text, is_bold=True)
        assert is_bold_heading(block) is False

    def test_starts_with_bullet(self) -> None:
        block = make_block("- Important point", is_bold=True)
        assert is_bold_heading(block) is False

    def test_allcaps_bold_not_matched(self) -> None:
        # All-caps handled by Rule B, not Rule C
        block = make_block("INTRODUCTION", is_bold=True)
        assert is_bold_heading(block) is False

    def test_empty_text(self) -> None:
        block = make_block("", is_bold=True)
        assert is_bold_heading(block) is False


# -----------------------------------------------------------------------
# is_fontsize_heading
# -----------------------------------------------------------------------


class TestIsFontsizeHeading:
    def test_level_1_large_font(self) -> None:
        block = make_block("Title", font_size=18.0)
        matched, level = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is True
        assert level == 1

    def test_level_2_medium_font(self) -> None:
        block = make_block("Subtitle", font_size=14.5)
        matched, level = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is True
        assert level == 2

    def test_body_font_not_heading(self) -> None:
        block = make_block("Body text", font_size=12.0)
        matched, _ = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is False

    def test_zero_font_size_not_heading(self) -> None:
        block = make_block("Text", font_size=0.0)
        matched, _ = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is False

    def test_zero_median_not_heading(self) -> None:
        block = make_block("Text", font_size=18.0)
        matched, _ = is_fontsize_heading(block, median_font_size=0.0)
        assert matched is False

    def test_exactly_threshold_level_2(self) -> None:
        block = make_block("Text", font_size=14.0)
        matched, level = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is True
        assert level == 2

    def test_exactly_threshold_level_1(self) -> None:
        block = make_block("Text", font_size=16.0)
        matched, level = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is True
        assert level == 1

    def test_slightly_larger_font_not_heading(self) -> None:
        block = make_block("Text", font_size=13.0)
        matched, _ = is_fontsize_heading(block, median_font_size=12.0)
        assert matched is False


# -----------------------------------------------------------------------
# is_excluded_section
# -----------------------------------------------------------------------


class TestIsExcludedSection:
    def test_references_excluded(self) -> None:
        assert is_excluded_section("References") is True

    def test_authors_excluded(self) -> None:
        assert is_excluded_section("Authors") is True

    def test_acknowledgments_excluded(self) -> None:
        assert is_excluded_section("Acknowledgments") is True

    def test_bibliography_excluded(self) -> None:
        assert is_excluded_section("Bibliography") is True

    def test_conflicts_excluded(self) -> None:
        assert is_excluded_section("Conflicts of Interest") is True

    def test_normal_section_not_excluded(self) -> None:
        assert is_excluded_section("Diagnosis") is False

    def test_case_insensitive(self) -> None:
        assert is_excluded_section("REFERENCES") is True

    def test_unknown_not_excluded(self) -> None:
        assert is_excluded_section("Unknown") is False


# -----------------------------------------------------------------------
# _compute_page_median_font_size
# -----------------------------------------------------------------------


class TestComputePageMedianFontSize:
    def test_basic_median(self) -> None:
        blocks = [
            make_block("a", font_size=10.0),
            make_block("b", font_size=12.0),
            make_block("c", font_size=14.0),
        ]
        assert _compute_page_median_font_size(blocks) == 12.0

    def test_zero_font_sizes_excluded(self) -> None:
        blocks = [
            make_block("a", font_size=0.0),
            make_block("b", font_size=12.0),
        ]
        assert _compute_page_median_font_size(blocks) == 12.0

    def test_all_zero_returns_zero(self) -> None:
        blocks = [make_block("a", font_size=0.0)]
        assert _compute_page_median_font_size(blocks) == 0.0

    def test_empty_blocks_returns_zero(self) -> None:
        assert _compute_page_median_font_size([]) == 0.0


# -----------------------------------------------------------------------
# _detect_heading (priority ordering)
# -----------------------------------------------------------------------


class TestDetectHeading:
    def test_numbered_wins_over_bold(self) -> None:
        block = make_block("1 Introduction", is_bold=True, font_size=18.0)
        matched, level, clean, htype = _detect_heading(block, "1 Introduction", 12.0)
        assert matched is True
        assert htype == "numbered"
        assert clean == "Introduction"

    def test_allcaps_wins_over_bold(self) -> None:
        block = make_block("INTRODUCTION", is_bold=True)
        matched, level, clean, htype = _detect_heading(block, "INTRODUCTION", 12.0)
        assert matched is True
        assert htype == "allcaps"

    def test_bold_wins_over_fontsize(self) -> None:
        block = make_block("Clinical Presentation", is_bold=True, font_size=16.0)
        matched, level, clean, htype = _detect_heading(
            block, "Clinical Presentation", 12.0
        )
        assert matched is True
        assert htype == "bold"

    def test_fontsize_matched_when_no_other_rule(self) -> None:
        block = make_block("Some heading", is_bold=False, font_size=18.0)
        matched, level, clean, htype = _detect_heading(block, "Some heading", 12.0)
        assert matched is True
        assert htype == "fontsize"

    def test_no_match_returns_false(self) -> None:
        block = make_block("Normal body text", is_bold=False, font_size=12.0)
        matched, _, _, htype = _detect_heading(block, "Normal body text", 12.0)
        assert matched is False
        assert htype is None


# -----------------------------------------------------------------------
# add_section_metadata
# -----------------------------------------------------------------------


class TestAddSectionMetadata:
    def test_returns_same_structure(self) -> None:
        doc = make_clean_doc()
        result = add_section_metadata(doc)
        assert "source_path" in result
        assert "pages" in result

    def test_all_blocks_get_section_fields(self) -> None:
        doc = make_clean_doc()
        result = add_section_metadata(doc)
        for page in result["pages"]:
            for block in page["blocks"]:
                assert "is_heading" in block
                assert "heading_level" in block
                assert "section_path" in block
                assert "section_title" in block
                assert "include_in_chunks" in block

    def test_numbered_heading_detected(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Introduction", block_id=0),
                        make_block("Some content", block_id=1),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        blocks = result["pages"][0]["blocks"]
        assert blocks[0]["is_heading"] is True
        assert blocks[0]["heading_level"] == 1
        assert blocks[0]["section_path"] == ["Introduction"]

    def test_section_path_inherited_by_content(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Introduction", block_id=0),
                        make_block("Content text", block_id=1),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        blocks = result["pages"][0]["blocks"]
        assert blocks[1]["section_path"] == ["Introduction"]
        assert blocks[1]["section_title"] == "Introduction"

    def test_nested_section_paths(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Diagnosis", block_id=0),
                        make_block("2.1 Tests", block_id=1),
                        make_block("Test content", block_id=2),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        blocks = result["pages"][0]["blocks"]
        assert blocks[1]["section_path"] == ["Diagnosis", "Tests"]
        assert blocks[2]["section_path"] == ["Diagnosis", "Tests"]

    def test_section_path_resets_on_new_level1(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Diagnosis", block_id=0),
                        make_block("2.1 Tests", block_id=1),
                        make_block("2 Treatment", block_id=2),
                        make_block("Content", block_id=3),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        blocks = result["pages"][0]["blocks"]
        assert blocks[2]["section_path"] == ["Treatment"]
        assert blocks[3]["section_path"] == ["Treatment"]

    def test_no_headings_all_unknown(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Just some text", block_id=0),
                        make_block("More text", block_id=1),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        for page in result["pages"]:
            for block in page["blocks"]:
                assert block["section_path"] == ["Unknown"]

    def test_heading_include_in_chunks_false(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Introduction", block_id=0),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        assert result["pages"][0]["blocks"][0]["include_in_chunks"] is False

    def test_content_include_in_chunks_true(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Introduction", block_id=0),
                        make_block("Content text", block_id=1),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        assert result["pages"][1 - 1]["blocks"][1]["include_in_chunks"] is True

    def test_excluded_section_include_in_chunks_false(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 References", block_id=0),
                        make_block("Smith et al 2020", block_id=1),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        blocks = result["pages"][0]["blocks"]
        assert blocks[1]["include_in_chunks"] is False

    def test_allcaps_heading_detected(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("INTRODUCTION", block_id=0),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        block = result["pages"][0]["blocks"][0]
        assert block["is_heading"] is True
        assert block["heading_level"] == 1
        assert block["section_path"] == ["INTRODUCTION"]

    def test_bold_heading_detected(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Clinical Presentation", block_id=0, is_bold=True),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        block = result["pages"][0]["blocks"][0]
        assert block["is_heading"] is True
        assert block["heading_level"] == 2

    def test_fontsize_heading_detected(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("Big Title", block_id=0, font_size=18.0),
                        make_block("Body text", block_id=1, font_size=12.0),
                        make_block("More body", block_id=2, font_size=12.0),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        assert result["pages"][0]["blocks"][0]["is_heading"] is True

    def test_false_positive_dosage_not_heading(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("2.5 mg dose", block_id=0),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        assert result["pages"][0]["blocks"][0]["is_heading"] is False

    def test_empty_block_not_heading(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("", block_id=0),
                    ],
                )
            ]
        )
        result = add_section_metadata(doc)
        assert result["pages"][0]["blocks"][0]["is_heading"] is False

    def test_deterministic(self) -> None:
        doc = make_clean_doc(
            pages=[
                make_page(
                    1,
                    blocks=[
                        make_block("1 Introduction", block_id=0),
                        make_block("Content", block_id=1),
                    ],
                )
            ]
        )
        result1 = add_section_metadata(doc)
        result2 = add_section_metadata(doc)
        assert result1 == result2

    def test_empty_document(self) -> None:
        doc = make_clean_doc(pages=[])
        result = add_section_metadata(doc)
        assert result["pages"] == []

    def test_source_path_preserved(self) -> None:
        doc = make_clean_doc()
        result = add_section_metadata(doc)
        assert result["source_path"] == "test.pdf"

from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.chunk import (
    MAX_CHUNK_TOKENS,
    MAX_MERGE_SECTIONS,
    MIN_CHUNK_TOKENS,
    OVERLAP_TOKENS,
    SHORT_SECTION_TOKENS,
    build_citation,
    chunk_document,
    chunk_section_group,
    clean_chunk_text,
    count_tokens,
    generate_chunk_id,
    group_blocks_by_section,
    make_table_chunk,
    merge_short_sections,
    split_into_sentences,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

LONG_SENTENCE = "This is a detailed clinical recommendation about the management of rheumatoid arthritis in adult patients. "


def make_block(
    text: str = "Body text about clinical guidelines.",
    block_id: int = 0,
    page_number: int = 1,
    block_uid: str = "uid001",
    section_path: list[str] | None = None,
    section_title: str = "Introduction",
    content_type: str = "text",
    include_in_chunks: bool = True,
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "block_uid": block_uid,
        "text": text,
        "page_number": page_number,
        "bbox": [10.0, 100.0, 500.0, 120.0],
        "font_size": 12.0,
        "is_heading": False,
        "include_in_chunks": include_in_chunks,
        "section_path": section_path or ["Introduction"],
        "section_title": section_title,
        "content_type": content_type,
    }


def make_doc_meta(
    doc_id: str = "doc123",
    doc_version: str = "v1",
    title: str = "RA Guidelines",
    source_name: str = "NICE",
    specialty: str = "rheumatology",
    author_org: str = "NICE",
    creation_date: str = "2020-01-01",
    last_updated_date: str = "2024-01-15",
    source_url: str = "https://nice.org.uk",
    ingestion_date: str = "2024-06-01",
) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "doc_version": doc_version,
        "title": title,
        "source_name": source_name,
        "specialty": specialty,
        "author_org": author_org,
        "creation_date": creation_date,
        "last_updated_date": last_updated_date,
        "source_url": source_url,
        "ingestion_date": ingestion_date,
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "doc_type": "guideline",
    }


def make_metadata_doc(
    pages: list[dict[str, Any]] | None = None,
    doc_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if doc_meta is None:
        doc_meta = make_doc_meta()
    if pages is None:
        pages = [{"page_number": 1, "blocks": [make_block()]}]
    return {
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "num_pages": len(pages),
        "needs_ocr": False,
        "doc_meta": doc_meta,
        "pages": pages,
    }


def long_text(n_sentences: int = 60) -> str:
    return LONG_SENTENCE * n_sentences

# -----------------------------------------------------------------------
# count_tokens
# -----------------------------------------------------------------------


class TestCountTokens:
    def test_empty_string(self) -> None:
        assert count_tokens("") == 0

    def test_single_word(self) -> None:
        assert count_tokens("hello") > 0

    def test_longer_text_more_tokens(self) -> None:
        assert count_tokens("hello world foo bar") > count_tokens("hello")

    def test_deterministic(self) -> None:
        text = "The patient was prescribed methotrexate."
        assert count_tokens(text) == count_tokens(text)

# -----------------------------------------------------------------------
# split_into_sentences
# -----------------------------------------------------------------------


class TestSplitIntoSentences:
    def test_single_sentence(self) -> None:
        result = split_into_sentences("This is a sentence.")
        assert len(result) == 1

    def test_multiple_sentences(self) -> None:
        result = split_into_sentences("First sentence. Second sentence. Third.")
        assert len(result) == 3

    def test_empty_string(self) -> None:
        assert split_into_sentences("") == []

    def test_medical_abbreviation_not_split(self) -> None:
        text = "Use DMARDs (e.g. methotrexate) first. Then biologics."
        result = split_into_sentences(text)
        assert len(result) == 2

    def test_whitespace_only_filtered(self) -> None:
        assert split_into_sentences("  ") == []

# -----------------------------------------------------------------------
# clean_chunk_text
# -----------------------------------------------------------------------


class TestCleanChunkText:
    def test_strips_whitespace(self) -> None:
        assert clean_chunk_text("  hello  ") == "hello"

    def test_collapses_triple_newlines(self) -> None:
        assert "\n\n\n" not in clean_chunk_text("a\n\n\n\nb")

    def test_preserves_double_newline(self) -> None:
        assert "\n\n" in clean_chunk_text("para one\n\npara two")

    def test_empty_string(self) -> None:
        assert clean_chunk_text("") == ""

# -----------------------------------------------------------------------
# generate_chunk_id
# -----------------------------------------------------------------------

class TestGenerateChunkId:
    def test_returns_16_char_hex(self) -> None:
        cid = generate_chunk_id("doc1", "v1", "some text")
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)

    def test_deterministic(self) -> None:
        assert generate_chunk_id("doc1", "v1", "text") == generate_chunk_id("doc1", "v1", "text")

    def test_different_text_different_id(self) -> None:
        assert generate_chunk_id("doc1", "v1", "text A") != generate_chunk_id("doc1", "v1", "text B")

    def test_different_version_different_id(self) -> None:
        assert generate_chunk_id("doc1", "v1", "text") != generate_chunk_id("doc1", "v2", "text")

    def test_content_based_not_positional(self) -> None:
        assert generate_chunk_id("doc1", "v1", "identical text") == generate_chunk_id("doc1", "v1", "identical text")

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.metadata import (
    MetadataValidationError,
    attach_metadata,
    extract_pdf_metadata,
    extract_title,
    generate_block_uid,
    generate_doc_id,
    generate_doc_version,
    infer_from_path,
    parse_pdf_date,
    validate_metadata,
    validate_source_info,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_block(
    text: str = "Body text",
    block_id: int = 0,
    page_number: int = 1,
    font_size: float = 12.0,
    include_in_chunks: bool = True,
    section_path: list[str] | None = None,
    section_title: str = "Introduction",
    content_type: str = "text",
) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "text": text,
        "page_number": page_number,
        "bbox": [10.0, 100.0, 500.0, 120.0],
        "font_size": font_size,
        "is_heading": False,
        "include_in_chunks": include_in_chunks,
        "section_path": section_path or ["Introduction"],
        "section_title": section_title,
        "content_type": content_type,
    }


def make_page(
    page_number: int = 1,
    blocks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if blocks is None:
        blocks = [make_block()]
    return {"page_number": page_number, "blocks": blocks}


def make_table_aware_doc(
    pages: list[dict[str, Any]] | None = None,
    source_path: str = "data/raw/rheumatology/NICE/test.pdf",
) -> dict[str, Any]:
    if pages is None:
        pages = [make_page()]
    return {
        "source_path": source_path,
        "num_pages": len(pages),
        "needs_ocr": False,
        "pages": pages,
    }


def make_source_info(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "source_name": "NICE",
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "doc_type": "guideline",
        "specialty": "rheumatology",
    }
    return {**defaults, **kwargs}


def make_pdf_metadata(
    title: str = "",
    mod_date: str = "",
    uid: str = "",
    creation_date: str = "",
) -> dict[str, Any]:
    return {
        "title": title,
        "author": "",
        "subject": "",
        "creator": "",
        "producer": "",
        "creationDate": creation_date,
        "modDate": mod_date,
        "uid": uid,
    }


def patch_pdf_meta(**kwargs: Any):  # type: ignore[no-untyped-def]
    return patch(
        "src.ingestion.metadata.extract_pdf_metadata",
        return_value=make_pdf_metadata(**kwargs),
    )

# -----------------------------------------------------------------------
# parse_pdf_date
# -----------------------------------------------------------------------


class TestParsePdfDate:
    def test_valid_date_parsed(self) -> None:
        assert parse_pdf_date("D:20240115120000") == "2024-01-15"

    def test_missing_prefix_returns_empty(self) -> None:
        assert parse_pdf_date("20240115") == ""

    def test_empty_string_returns_empty(self) -> None:
        assert parse_pdf_date("") == ""

    def test_too_short_returns_empty(self) -> None:
        assert parse_pdf_date("D:202") == ""

    def test_d_prefix_only_returns_empty(self) -> None:
        assert parse_pdf_date("D:") == ""

# -----------------------------------------------------------------------
# infer_from_path
# -----------------------------------------------------------------------


class TestInferFromPath:
    def test_infers_specialty_and_source_name(self) -> None:
        result = infer_from_path("data/raw/rheumatology/BSR/guideline.pdf")
        assert result["specialty"] == "rheumatology"
        assert result["source_name"] == "BSR"

    def test_infers_neurology_nice(self) -> None:
        result = infer_from_path("data/raw/neurology/NICE/guideline.pdf")
        assert result["specialty"] == "neurology"
        assert result["source_name"] == "NICE"

    def test_missing_raw_returns_empty(self) -> None:
        result = infer_from_path("/downloads/guideline.pdf")
        assert result["specialty"] == ""
        assert result["source_name"] == ""

    def test_raw_at_end_returns_empty(self) -> None:
        result = infer_from_path("/data/raw")
        assert result["specialty"] == ""
        assert result["source_name"] == ""

    def test_absolute_path_works(self) -> None:
        result = infer_from_path(
            "/home/kavin/Desktop/Ambience-AI-1.5/rag_service/data/raw/rheumatology/Others/file.pdf"
        )
        assert result["specialty"] == "rheumatology"
        assert result["source_name"] == "Others"
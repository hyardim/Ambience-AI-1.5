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

# -----------------------------------------------------------------------
# validate_source_info
# -----------------------------------------------------------------------


class TestValidateSourceInfo:
    def test_valid_source_info_passes(self) -> None:
        validate_source_info(make_source_info())

    def test_missing_required_field_raises(self) -> None:
        info = make_source_info()
        del info["specialty"]
        with pytest.raises(MetadataValidationError, match="specialty"):
            validate_source_info(info)

    def test_invalid_specialty_raises(self) -> None:
        with pytest.raises(MetadataValidationError, match="Invalid specialty"):
            validate_source_info(make_source_info(specialty="cardiology"))

    def test_invalid_source_name_raises(self) -> None:
        with pytest.raises(MetadataValidationError, match="Invalid source_name"):
            validate_source_info(make_source_info(source_name="NHS"))

    def test_invalid_doc_type_raises(self) -> None:
        with pytest.raises(MetadataValidationError, match="Invalid doc_type"):
            validate_source_info(make_source_info(doc_type="leaflet"))

    def test_all_valid_specialties_pass(self) -> None:
        for specialty in ["neurology", "rheumatology"]:
            validate_source_info(make_source_info(specialty=specialty))

    def test_all_valid_source_names_pass(self) -> None:
        for source_name in ["NICE", "BSR", "Others"]:
            validate_source_info(make_source_info(source_name=source_name))

# -----------------------------------------------------------------------
# extract_pdf_metadata
# -----------------------------------------------------------------------


class TestExtractPdfMetadata:
    def test_extracts_title_and_dates(self) -> None:
        mock_metadata = {
            "title": "RA Guidelines",
            "author": "NICE",
            "subject": "",
            "creator": "",
            "producer": "",
            "creationDate": "D:20240101000000",
            "modDate": "D:20240115000000",
            "uid": "abc123",
        }
        mock_doc = MagicMock()
        mock_doc.metadata = mock_metadata
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("src.ingestion.metadata.fitz.open", return_value=mock_doc):
            result = extract_pdf_metadata("test.pdf")

        assert result["title"] == "RA Guidelines"
        assert result["creationDate"] == "2024-01-01"
        assert result["modDate"] == "2024-01-15"
        assert result["uid"] == "abc123"

    def test_exception_returns_empty_dict(self) -> None:
        with patch(
            "src.ingestion.metadata.fitz.open",
            side_effect=Exception("file error"),
        ):
            result = extract_pdf_metadata("missing.pdf")

        assert result["title"] == ""
        assert result["creationDate"] == ""
        assert result["modDate"] == ""

    def test_missing_keys_default_to_empty(self) -> None:
        mock_doc = MagicMock()
        mock_doc.metadata = {}
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        with patch("src.ingestion.metadata.fitz.open", return_value=mock_doc):
            result = extract_pdf_metadata("test.pdf")

        assert result["title"] == ""
        assert result["uid"] == ""

# -----------------------------------------------------------------------
# extract_title
# -----------------------------------------------------------------------


class TestExtractTitle:
    def test_pdf_metadata_title_used(self) -> None:
        doc = make_table_aware_doc()
        pdf_meta = make_pdf_metadata(title="RA Guidelines 2024")
        assert extract_title(doc, pdf_meta, make_source_info()) == "RA Guidelines 2024"

    def test_generic_title_skipped(self) -> None:
        doc = make_table_aware_doc(pages=[
            make_page(blocks=[make_block("Big Title", font_size=24.0)])
        ])
        pdf_meta = make_pdf_metadata(title="Untitled")
        assert extract_title(doc, pdf_meta, make_source_info()) == "Big Title"

    def test_large_font_block_used_when_no_pdf_title(self) -> None:
        doc = make_table_aware_doc(pages=[
            make_page(blocks=[make_block("Clinical Guideline", font_size=22.0)])
        ])
        assert extract_title(doc, make_pdf_metadata(), make_source_info()) == "Clinical Guideline"

    def test_small_font_block_not_used_as_title(self) -> None:
        doc = make_table_aware_doc(pages=[
            make_page(blocks=[make_block("Body text", font_size=12.0)])
        ])
        source_info = make_source_info(
            source_path="data/raw/rheumatology/NICE/nice_ra_2024.pdf"
        )
        assert extract_title(doc, make_pdf_metadata(), source_info) == "Nice Ra 2024"

    def test_filename_fallback_no_pages(self) -> None:
        doc = make_table_aware_doc(pages=[])
        source_info = make_source_info(
            source_path="data/raw/rheumatology/NICE/nice_ra_guidelines.pdf"
        )
        assert extract_title(doc, make_pdf_metadata(), source_info) == "Nice Ra Guidelines"

    def test_empty_first_page_blocks_falls_back_to_filename(self) -> None:
        doc = make_table_aware_doc(pages=[make_page(blocks=[])])
        source_info = make_source_info(
            source_path="data/raw/neurology/BSR/bsr_guidelines.pdf"
        )
        assert extract_title(doc, make_pdf_metadata(), source_info) == "Bsr Guidelines"

# -----------------------------------------------------------------------
# generate_doc_id
# -----------------------------------------------------------------------


class TestGenerateDocId:
    def test_external_id_used_first(self) -> None:
        doc = make_table_aware_doc()
        pdf_meta = make_pdf_metadata(uid="pdf-uid-123")
        source_info = make_source_info(external_id="NICE-NG100")
        assert generate_doc_id(doc, pdf_meta, source_info) == "NICE-NG100"

    def test_pdf_uid_used_second(self) -> None:
        doc = make_table_aware_doc()
        pdf_meta = make_pdf_metadata(uid="pdf-uid-123")
        assert generate_doc_id(doc, pdf_meta, make_source_info()) == "pdf-uid-123"

    def test_content_hash_fallback(self) -> None:
        result = generate_doc_id(
            make_table_aware_doc(), make_pdf_metadata(), make_source_info()
        )
        assert len(result) == 16
        assert result.isalnum()

    def test_content_hash_stable_regardless_of_path(self) -> None:
        doc = make_table_aware_doc(
            pages=[make_page(blocks=[make_block("Same content")])]
        )
        pdf_meta = make_pdf_metadata()
        id1 = generate_doc_id(
            doc, pdf_meta,
            make_source_info(source_path="data/raw/rheumatology/NICE/a.pdf", author_org="NICE"),
        )
        id2 = generate_doc_id(
            doc, pdf_meta,
            make_source_info(source_path="data/raw/rheumatology/NICE/b/a.pdf", author_org="NICE"),
        )
        assert id1 == id2

    def test_different_content_gives_different_id(self) -> None:
        pdf_meta = make_pdf_metadata()
        source_info = make_source_info()
        id1 = generate_doc_id(
            make_table_aware_doc(pages=[make_page(blocks=[make_block("Content A")])]),
            pdf_meta, source_info,
        )
        id2 = generate_doc_id(
            make_table_aware_doc(pages=[make_page(blocks=[make_block("Content B")])]),
            pdf_meta, source_info,
        )
        assert id1 != id2

# -----------------------------------------------------------------------
# generate_doc_version
# -----------------------------------------------------------------------


class TestGenerateDocVersion:
    def test_external_version_used_first(self) -> None:
        assert generate_doc_version(
            make_table_aware_doc(),
            make_pdf_metadata(mod_date="2024-01-15"),
            make_source_info(version="v2.1"),
        ) == "v2.1"

    def test_mod_date_used_second(self) -> None:
        assert generate_doc_version(
            make_table_aware_doc(),
            make_pdf_metadata(mod_date="2024-01-15"),
            make_source_info(),
        ) == "2024-01-15"

    def test_page_hash_fallback(self) -> None:
        result = generate_doc_version(
            make_table_aware_doc(), make_pdf_metadata(), make_source_info()
        )
        assert len(result) == 8
        assert result.isalnum()

    def test_changed_content_gives_different_version(self) -> None:
        pdf_meta = make_pdf_metadata()
        source_info = make_source_info()
        v1 = generate_doc_version(
            make_table_aware_doc(pages=[make_page(blocks=[make_block("Version 1")])]),
            pdf_meta, source_info,
        )
        v2 = generate_doc_version(
            make_table_aware_doc(pages=[make_page(blocks=[make_block("Version 2")])]),
            pdf_meta, source_info,
        )
        assert v1 != v2

    def test_unchanged_content_gives_same_version(self) -> None:
        doc = make_table_aware_doc()
        pdf_meta = make_pdf_metadata()
        source_info = make_source_info()
        assert (
            generate_doc_version(doc, pdf_meta, source_info)
            == generate_doc_version(doc, pdf_meta, source_info)
        )

# -----------------------------------------------------------------------
# generate_block_uid
# -----------------------------------------------------------------------


class TestGenerateBlockUid:
    def test_returns_16_char_hex(self) -> None:
        uid = generate_block_uid("doc123", 1, 0, "some text")
        assert len(uid) == 16
        assert all(c in "0123456789abcdef" for c in uid)

    def test_same_inputs_same_uid(self) -> None:
        assert (
            generate_block_uid("doc123", 1, 0, "text")
            == generate_block_uid("doc123", 1, 0, "text")
        )

    def test_different_text_different_uid(self) -> None:
        assert (
            generate_block_uid("doc123", 1, 0, "text A")
            != generate_block_uid("doc123", 1, 0, "text B")
        )

    def test_different_page_different_uid(self) -> None:
        assert (
            generate_block_uid("doc123", 1, 0, "text")
            != generate_block_uid("doc123", 2, 0, "text")
        )

    def test_case_insensitive(self) -> None:
        assert (
            generate_block_uid("doc123", 1, 0, "HELLO WORLD")
            == generate_block_uid("doc123", 1, 0, "hello world")
        )

    def test_whitespace_normalized(self) -> None:
        assert (
            generate_block_uid("doc123", 1, 0, "  hello  ")
            == generate_block_uid("doc123", 1, 0, "hello")
        )

# -----------------------------------------------------------------------
# validate_metadata
# -----------------------------------------------------------------------


class TestValidateMetadata:
    def _make_valid_doc(self) -> dict[str, Any]:
        return {
            "doc_meta": {
                "doc_id": "abc123",
                "doc_version": "v1",
                "title": "Guidelines",
                "source_name": "NICE",
                "doc_type": "guideline",
                "specialty": "rheumatology",
                "source_path": "data/raw/rheumatology/NICE/test.pdf",
                "ingestion_date": "2024-01-15",
            },
            "pages": [
                {
                    "page_number": 1,
                    "blocks": [
                        {
                            "block_id": 0,
                            "block_uid": "uid123",
                            "page_number": 1,
                            "section_path": ["Introduction"],
                            "section_title": "Introduction",
                            "content_type": "text",
                            "include_in_chunks": True,
                        }
                    ],
                }
            ],
        }

    def test_valid_doc_passes(self) -> None:
        assert validate_metadata(self._make_valid_doc()) is True

    def test_missing_doc_meta_raises(self) -> None:
        doc = self._make_valid_doc()
        del doc["doc_meta"]
        with pytest.raises(MetadataValidationError, match="Missing doc_meta"):
            validate_metadata(doc)

    def test_missing_doc_field_raises(self) -> None:
        doc = self._make_valid_doc()
        del doc["doc_meta"]["doc_id"]
        with pytest.raises(MetadataValidationError, match="Missing doc_meta.doc_id"):
            validate_metadata(doc)

    def test_empty_doc_field_raises(self) -> None:
        doc = self._make_valid_doc()
        doc["doc_meta"]["title"] = ""
        with pytest.raises(MetadataValidationError, match="Empty doc_meta.title"):
            validate_metadata(doc)

    def test_missing_specialty_raises(self) -> None:
        doc = self._make_valid_doc()
        del doc["doc_meta"]["specialty"]
        with pytest.raises(MetadataValidationError, match="Missing doc_meta.specialty"):
            validate_metadata(doc)

    def test_missing_block_field_raises(self) -> None:
        doc = self._make_valid_doc()
        del doc["pages"][0]["blocks"][0]["block_uid"]
        with pytest.raises(MetadataValidationError, match="Block missing block_uid"):
            validate_metadata(doc)

    def test_invalid_section_path_type_raises(self) -> None:
        doc = self._make_valid_doc()
        doc["pages"][0]["blocks"][0]["section_path"] = "Introduction"
        with pytest.raises(MetadataValidationError, match="section_path must be list"):
            validate_metadata(doc)

    def test_invalid_include_in_chunks_type_raises(self) -> None:
        doc = self._make_valid_doc()
        doc["pages"][0]["blocks"][0]["include_in_chunks"] = "yes"
        with pytest.raises(
            MetadataValidationError, match="include_in_chunks must be bool"
        ):
            validate_metadata(doc)

    def test_empty_pages_passes(self) -> None:
        doc = self._make_valid_doc()
        doc["pages"] = []
        assert validate_metadata(doc) is True
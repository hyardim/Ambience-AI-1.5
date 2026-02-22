from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.ingestion.pipeline import (
    PipelineError,
    _strip_embeddings,
    discover_pdfs,
    load_ingestion_config,
    load_sources,
    run_ingestion,
    run_pipeline,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

FAKE_SOURCE_INFO = {
    "source_name": "NICE",
    "author_org": "NICE",
    "specialty": "rheumatology",
    "doc_type": "guideline",
    "source_url": "https://www.nice.org.uk",
}

FAKE_DOC_META = {
    "doc_id": "abc123",
    "doc_version": "v1",
    "title": "RA Guidelines",
    "source_name": "NICE",
    "specialty": "rheumatology",
    "doc_type": "guideline",
    "source_path": "/data/raw/NICE/test.pdf",
    "ingestion_date": "2024-01-01",
    "author_org": "NICE",
    "source_url": "https://nice.org.uk",
    "creation_date": "",
    "publish_date": "",
    "last_updated_date": "",
}


def make_raw_doc() -> dict[str, Any]:
    return {
        "source_path": "/data/raw/NICE/test.pdf",
        "num_pages": 2,
        "needs_ocr": False,
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": 0,
                        "text": "Introduction",
                        "bbox": [0, 0, 100, 20],
                        "font_size": 14.0,
                        "font_name": "Arial",
                        "is_bold": True,
                    }
                ],
            }
        ],
    }


def make_embedded_doc() -> dict[str, Any]:
    return {
        "source_path": "/data/raw/NICE/test.pdf",
        "num_pages": 2,
        "needs_ocr": False,
        "doc_meta": FAKE_DOC_META,
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "block_id": 0,
                        "text": "Some text",
                        "bbox": [0, 0, 100, 20],
                        "font_size": 12.0,
                        "font_name": "Arial",
                        "is_bold": False,
                        "is_heading": False,
                        "content_type": "text",
                        "include_in_chunks": True,
                        "section_path": ["Introduction"],
                        "section_title": "Introduction",
                        "page_number": 1,
                        "block_uid": "uid001",
                    }
                ],
            }
        ],
        "chunks": [
            {
                "chunk_id": "chunk001",
                "chunk_index": 0,
                "content_type": "text",
                "text": "Some text",
                "section_path": ["Introduction"],
                "section_title": "Introduction",
                "page_start": 1,
                "page_end": 1,
                "block_uids": ["uid001"],
                "token_count": 10,
                "embedding": [0.1] * 384,
                "embedding_status": "success",
                "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
                "embedding_model_version": "main",
                "embedding_dimensions": 384,
                "embedding_error": None,
                "citation": {},
            }
        ],
    }


def make_db_report(
    inserted: int = 1,
    updated: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> dict[str, int]:
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }


PIPELINE_PATCHES = [
    "src.ingestion.pipeline.extract_raw_document",
    "src.ingestion.pipeline.clean_document",
    "src.ingestion.pipeline.add_section_metadata",
    "src.ingestion.pipeline.detect_and_convert_tables",
    "src.ingestion.pipeline.attach_metadata",
    "src.ingestion.pipeline.chunk_document",
    "src.ingestion.pipeline.embed_chunks",
    "src.ingestion.pipeline.store_chunks",
]


def make_all_patches(embedded_doc: dict[str, Any] | None = None) -> dict[str, MagicMock]:
    doc = embedded_doc or make_embedded_doc()
    raw = make_raw_doc()
    mocks = {}
    return_values = [raw, raw, raw, raw, doc, doc, doc, make_db_report()]
    for patch_path, rv in zip(PIPELINE_PATCHES, return_values):
        m = MagicMock(return_value=rv)
        mocks[patch_path] = m
    return mocks



# -----------------------------------------------------------------------
# _strip_embeddings
# -----------------------------------------------------------------------


class TestStripEmbeddings:
    def test_strips_embedding_vectors(self) -> None:
        doc = make_embedded_doc()
        stripped = _strip_embeddings(doc)
        assert stripped["chunks"][0]["embedding"] == "<stripped>"

    def test_original_unchanged(self) -> None:
        doc = make_embedded_doc()
        _strip_embeddings(doc)
        assert doc["chunks"][0]["embedding"] == [0.1] * 384

    def test_no_chunks_returns_doc(self) -> None:
        doc = {"source_path": "x.pdf", "chunks": []}
        stripped = _strip_embeddings(doc)
        assert stripped["chunks"] == []
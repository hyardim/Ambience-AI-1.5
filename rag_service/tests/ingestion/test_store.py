from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from src.ingestion.store import (
    _build_metadata,
    _metadata_json,
    _upsert_chunk,
    store_chunks,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_chunk(
    chunk_id: str = "chunk001",
    text: str = "Some clinical text.",
    content_type: str = "text",
    chunk_index: int = 0,
    embedding_status: str = "success",
    section_path: list[str] | None = None,
    section_title: str = "Introduction",
    page_start: int = 1,
    page_end: int = 1,
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "content_type": content_type,
        "text": text,
        "section_path": section_path or ["Introduction"],
        "section_title": section_title,
        "page_start": page_start,
        "page_end": page_end,
        "block_uids": ["uid001"],
        "token_count": 10,
        "embedding": [0.1] * 384,
        "embedding_status": embedding_status,
        "embedding_model_name": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_model_version": "main",
        "embedding_dimensions": 384,
        "embedding_error": None,
        "citation": {
            "doc_id": "doc123",
            "source_name": "NICE",
            "specialty": "rheumatology",
            "title": "RA Guidelines",
            "author_org": "NICE",
            "creation_date": "2020-01-01",
            "last_updated_date": "2024-01-15",
            "section_path": section_path or ["Introduction"],
            "section_title": section_title,
            "page_range": "1",
            "source_url": "https://nice.org.uk",
            "access_date": "2024-06-01",
        },
    }


def make_embedded_doc(
    chunks: list[dict[str, Any]] | None = None,
    doc_id: str = "doc123",
    doc_version: str = "v1",
) -> dict[str, Any]:
    return {
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "num_pages": 1,
        "needs_ocr": False,
        "doc_meta": {
            "doc_id": doc_id,
            "doc_version": doc_version,
            "title": "RA Guidelines",
            "source_name": "NICE",
        },
        "chunks": chunks if chunks is not None else [make_chunk()],
    }


def make_mock_conn(existing_row: tuple | None = None) -> MagicMock:
    """Create a mock psycopg2 connection."""
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = existing_row
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cur

# -----------------------------------------------------------------------
# _build_metadata
# -----------------------------------------------------------------------


class TestBuildMetadata:
    def test_all_required_keys_present(self) -> None:
        chunk = make_chunk()
        metadata = _build_metadata(chunk)
        for key in [
            "source_name",
            "title",
            "section_path",
            "section_title",
            "page_start",
            "page_end",
            "citation",
        ]:
            assert key in metadata

    def test_source_name_from_citation(self) -> None:
        chunk = make_chunk()
        metadata = _build_metadata(chunk)
        assert metadata["source_name"] == "NICE"

    def test_section_path_correct(self) -> None:
        chunk = make_chunk(section_path=["Treatment", "DMARDs"])
        metadata = _build_metadata(chunk)
        assert metadata["section_path"] == ["Treatment", "DMARDs"]

    def test_page_range_correct(self) -> None:
        chunk = make_chunk(page_start=3, page_end=5)
        metadata = _build_metadata(chunk)
        assert metadata["page_start"] == 3
        assert metadata["page_end"] == 5

    def test_citation_embedded(self) -> None:
        chunk = make_chunk()
        metadata = _build_metadata(chunk)
        assert isinstance(metadata["citation"], dict)
        assert metadata["citation"]["doc_id"] == "doc123"

# -----------------------------------------------------------------------
# _metadata_json
# -----------------------------------------------------------------------


class TestMetadataJson:
    def test_returns_string(self) -> None:
        assert isinstance(_metadata_json({"a": 1}), str)

    def test_sorted_keys(self) -> None:
        result = _metadata_json({"b": 2, "a": 1})
        assert result.index('"a"') < result.index('"b"')

    def test_deterministic(self) -> None:
        meta = {"b": 2, "a": 1, "c": [1, 2, 3]}
        assert _metadata_json(meta) == _metadata_json(meta)

    def test_different_metadata_different_json(self) -> None:
        assert _metadata_json({"a": 1}) != _metadata_json({"a": 2})

# -----------------------------------------------------------------------
# _upsert_chunk
# -----------------------------------------------------------------------


class TestUpsertChunk:
    def test_inserts_new_chunk(self) -> None:
        conn, cur = make_mock_conn(existing_row=None)
        result = _upsert_chunk(conn, make_chunk(), "doc123", "v1")
        assert result == "inserted"
        assert cur.execute.call_count == 2  # SELECT + INSERT
        conn.commit.assert_called_once()

    def test_skips_identical_chunk(self) -> None:
        chunk = make_chunk()
        metadata = _build_metadata(chunk)
        existing_row = (chunk["text"], metadata)
        conn, cur = make_mock_conn(existing_row=existing_row)
        result = _upsert_chunk(conn, chunk, "doc123", "v1")
        assert result == "skipped"
        conn.commit.assert_not_called()

    def test_updates_on_text_change(self) -> None:
        chunk = make_chunk(text="New text.")
        existing_row = ("Old text.", _build_metadata(chunk))
        conn, cur = make_mock_conn(existing_row=existing_row)
        result = _upsert_chunk(conn, chunk, "doc123", "v1")
        assert result == "updated"
        conn.commit.assert_called_once()

    def test_updates_on_metadata_change(self) -> None:
        chunk = make_chunk()
        old_metadata = {"source_name": "OLD", "title": "Old Title",
                        "section_path": [], "section_title": "",
                        "page_start": 0, "page_end": 0, "citation": {}}
        existing_row = (chunk["text"], old_metadata)
        conn, cur = make_mock_conn(existing_row=existing_row)
        result = _upsert_chunk(conn, chunk, "doc123", "v1")
        assert result == "updated"
        conn.commit.assert_called_once()

    def test_raises_on_db_error(self) -> None:
        conn, cur = make_mock_conn(existing_row=None)
        cur.execute.side_effect = Exception("DB error")
        with pytest.raises(Exception, match="DB error"):
            _upsert_chunk(conn, make_chunk(), "doc123", "v1")

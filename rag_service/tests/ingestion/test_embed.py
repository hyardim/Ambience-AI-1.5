from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import src.ingestion.embed as embed_module
from src.ingestion.embed import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    MAX_RETRIES,
    _embed_batch,
    _embed_single,
    _make_failure_fields,
    _make_success_fields,
    embed_chunks,
)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_chunk(
    chunk_id: str = "abc123",
    text: str = "Some clinical guideline text.",
    content_type: str = "text",
    chunk_index: int = 0,
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "content_type": content_type,
        "text": text,
        "section_path": ["Introduction"],
        "section_title": "Introduction",
        "page_start": 1,
        "page_end": 1,
        "block_uids": ["uid001"],
        "token_count": 10,
        "citation": {
            "doc_id": "doc123",
            "source_name": "NICE",
            "specialty": "rheumatology",
            "title": "RA Guidelines",
            "author_org": "NICE",
            "creation_date": "2020-01-01",
            "last_updated_date": "2024-01-15",
            "section_path": ["Introduction"],
            "section_title": "Introduction",
            "page_range": "1",
            "source_url": "https://nice.org.uk",
            "access_date": "2024-06-01",
        },
    }


def make_chunked_doc(
    chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if chunks is None:
        chunks = [make_chunk()]
    return {
        "source_path": "data/raw/rheumatology/NICE/test.pdf",
        "num_pages": 1,
        "needs_ocr": False,
        "doc_meta": {"doc_id": "doc123", "title": "RA Guidelines"},
        "chunks": chunks,
    }


def make_fake_vector(dim: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return [0.1] * dim


def make_mock_model(
    vectors: list[list[float]] | None = None,
    fail: bool = False,
) -> MagicMock:
    model = MagicMock()
    if fail:
        model.encode.side_effect = RuntimeError("model error")
    else:
        def encode_side_effect(texts, **kwargs):  # type: ignore[no-untyped-def]
            n = len(texts)
            vecs = vectors if vectors else [make_fake_vector() for _ in range(n)]
            return np.array(vecs[:n])
        model.encode.side_effect = encode_side_effect
    return model

# -----------------------------------------------------------------------
# _make_success_fields
# -----------------------------------------------------------------------


class TestMakeSuccessFields:
    def test_all_fields_present(self) -> None:
        fields = _make_success_fields(make_fake_vector())
        assert fields["embedding_status"] == "success"
        assert fields["embedding_model_name"] == EMBEDDING_MODEL_NAME
        assert fields["embedding_model_version"] == EMBEDDING_MODEL_VERSION
        assert fields["embedding_dimensions"] == EMBEDDING_DIMENSIONS
        assert fields["embedding_error"] is None

    def test_embedding_value_set(self) -> None:
        vec = make_fake_vector()
        fields = _make_success_fields(vec)
        assert fields["embedding"] == vec

    def test_embedding_length_correct(self) -> None:
        fields = _make_success_fields(make_fake_vector())
        assert len(fields["embedding"]) == EMBEDDING_DIMENSIONS


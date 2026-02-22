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

# -----------------------------------------------------------------------
# _make_failure_fields
# -----------------------------------------------------------------------


class TestMakeFailureFields:
    def test_all_fields_present(self) -> None:
        fields = _make_failure_fields("timeout error")
        assert fields["embedding_status"] == "failed"
        assert fields["embedding"] is None
        assert fields["embedding_error"] == "timeout error"
        assert fields["embedding_model_name"] == EMBEDDING_MODEL_NAME
        assert fields["embedding_model_version"] == EMBEDDING_MODEL_VERSION
        assert fields["embedding_dimensions"] == EMBEDDING_DIMENSIONS

    def test_error_message_stored(self) -> None:
        fields = _make_failure_fields("OOM error")
        assert fields["embedding_error"] == "OOM error"

# -----------------------------------------------------------------------
# _embed_batch
# -----------------------------------------------------------------------


class TestEmbedBatch:
    def test_returns_vectors_for_each_text(self) -> None:
        model = make_mock_model()
        result = _embed_batch(model, ["text one", "text two", "text three"])
        assert len(result) == 3

    def test_each_vector_is_list_of_floats(self) -> None:
        model = make_mock_model()
        result = _embed_batch(model, ["hello"])
        assert isinstance(result[0], list)
        assert all(isinstance(x, float) for x in result[0])

    def test_retries_on_failure(self) -> None:
        model = MagicMock()
        call_count = 0

        def encode_side_effect(texts, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient error")
            return np.array([make_fake_vector()])

        model.encode.side_effect = encode_side_effect

        with patch("src.ingestion.embed.time.sleep"):
            result = _embed_batch(model, ["text"])

        assert call_count == 2
        assert len(result) == 1

    def test_raises_after_max_retries(self) -> None:
        model = make_mock_model(fail=True)
        with patch("src.ingestion.embed.time.sleep"):
            with pytest.raises(RuntimeError):
                _embed_batch(model, ["text"])

    def test_encode_called_once_on_success(self) -> None:
        model = make_mock_model()
        _embed_batch(model, ["text one", "text two"])
        assert model.encode.call_count == 1


# -----------------------------------------------------------------------
# _embed_single
# -----------------------------------------------------------------------


class TestEmbedSingle:
    def test_returns_vector_on_success(self) -> None:
        model = make_mock_model()
        result = _embed_single(model, "some text")
        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIMENSIONS

    def test_returns_none_after_max_retries(self) -> None:
        model = make_mock_model(fail=True)
        with patch("src.ingestion.embed.time.sleep"):
            result = _embed_single(model, "some text")
        assert result is None

    def test_retries_on_transient_failure(self) -> None:
        model = MagicMock()
        call_count = 0

        def encode_side_effect(texts, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("transient")
            return np.array([make_fake_vector()])

        model.encode.side_effect = encode_side_effect

        with patch("src.ingestion.embed.time.sleep"):
            result = _embed_single(model, "text")

        assert result is not None
        assert call_count == 2

# -----------------------------------------------------------------------
# embed_chunks (integration)
# -----------------------------------------------------------------------


class TestEmbedChunks:
    def test_all_chunks_embedded_successfully(self) -> None:
        doc = make_chunked_doc(chunks=[make_chunk(f"c{i}") for i in range(3)])
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            result = embed_chunks(doc)
        for chunk in result["chunks"]:
            assert chunk["embedding_status"] == "success"

    def test_embedding_dimensions_correct(self) -> None:
        doc = make_chunked_doc()
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            result = embed_chunks(doc)
        assert len(result["chunks"][0]["embedding"]) == EMBEDDING_DIMENSIONS

    def test_all_metadata_fields_present_on_success(self) -> None:
        doc = make_chunked_doc()
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            result = embed_chunks(doc)
        chunk = result["chunks"][0]
        for field in [
            "embedding",
            "embedding_status",
            "embedding_model_name",
            "embedding_model_version",
            "embedding_dimensions",
            "embedding_error",
        ]:
            assert field in chunk

    def test_batch_size_respected(self) -> None:
        n_chunks = EMBEDDING_BATCH_SIZE + 5
        doc = make_chunked_doc(chunks=[make_chunk(f"c{i}") for i in range(n_chunks)])
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            embed_chunks(doc)
        assert model.encode.call_count >= 2

    def test_failed_batch_falls_back_to_per_chunk(self) -> None:
        doc = make_chunked_doc(chunks=[make_chunk("c1"), make_chunk("c2")])
        model = MagicMock()

        def encode_side_effect(texts, **kwargs):  # type: ignore[no-untyped-def]
            if len(texts) > 1:
                raise RuntimeError("batch error")
            return np.array([make_fake_vector()])

        model.encode.side_effect = encode_side_effect

        with patch("src.ingestion.embed._load_model", return_value=model), \
             patch("src.ingestion.embed.time.sleep"):
            result = embed_chunks(doc)

        assert all(c["embedding_status"] == "success" for c in result["chunks"])

    def test_quarantined_chunk_has_failed_status(self) -> None:
        doc = make_chunked_doc(chunks=[make_chunk("fail_chunk")])
        model = make_mock_model(fail=True)
        with patch("src.ingestion.embed._load_model", return_value=model), \
             patch("src.ingestion.embed.time.sleep"):
            result = embed_chunks(doc)
        chunk = result["chunks"][0]
        assert chunk["embedding_status"] == "failed"
        assert chunk["embedding"] is None

    def test_pipeline_continues_after_quarantine(self) -> None:
        fail_chunk = make_chunk("fail", text="bad text")
        ok_chunk = make_chunk("ok", text="good text")
        doc = make_chunked_doc(chunks=[fail_chunk, ok_chunk])
        model = MagicMock()

        def encode_side_effect(texts, **kwargs):  # type: ignore[no-untyped-def]
            if len(texts) > 1:
                raise RuntimeError("batch fail")
            if texts[0] == "bad text":
                raise RuntimeError("single fail")
            return np.array([make_fake_vector()])

        model.encode.side_effect = encode_side_effect

        with patch("src.ingestion.embed._load_model", return_value=model), \
             patch("src.ingestion.embed.time.sleep"):
            result = embed_chunks(doc)

        statuses = {c["chunk_id"]: c["embedding_status"] for c in result["chunks"]}
        assert statuses["fail"] == "failed"
        assert statuses["ok"] == "success"

    def test_error_message_recorded_on_failed_chunk(self) -> None:
        doc = make_chunked_doc(chunks=[make_chunk("fail_chunk")])
        model = make_mock_model(fail=True)
        with patch("src.ingestion.embed._load_model", return_value=model), \
             patch("src.ingestion.embed.time.sleep"):
            result = embed_chunks(doc)
        chunk = result["chunks"][0]
        assert chunk["embedding_error"] is not None
        assert len(chunk["embedding_error"]) > 0

    def test_empty_document_returns_empty_chunks(self) -> None:
        doc = make_chunked_doc(chunks=[])
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            result = embed_chunks(doc)
        assert result["chunks"] == []

    def test_original_doc_fields_preserved(self) -> None:
        doc = make_chunked_doc()
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            result = embed_chunks(doc)
        assert result["source_path"] == doc["source_path"]
        assert result["doc_meta"] == doc["doc_meta"]

    def test_model_loaded_once(self) -> None:
        doc = make_chunked_doc(chunks=[make_chunk(f"c{i}") for i in range(5)])
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model) as mock_load:
            embed_chunks(doc)
        mock_load.assert_called_once()

    def test_deterministic_same_input_same_embedding(self) -> None:
        vec = [float(i) / 384 for i in range(384)]
        model = MagicMock()
        model.encode.return_value = np.array([vec])

        with patch("src.ingestion.embed._load_model", return_value=model):
            result1 = embed_chunks(make_chunked_doc())
        with patch("src.ingestion.embed._load_model", return_value=model):
            result2 = embed_chunks(make_chunked_doc())

        assert result1["chunks"][0]["embedding"] == result2["chunks"][0]["embedding"]

    def test_embedding_model_name_on_all_chunks(self) -> None:
        doc = make_chunked_doc(chunks=[make_chunk(f"c{i}") for i in range(3)])
        model = make_mock_model()
        with patch("src.ingestion.embed._load_model", return_value=model):
            result = embed_chunks(doc)
        for chunk in result["chunks"]:
            assert chunk["embedding_model_name"] == EMBEDDING_MODEL_NAME
            assert chunk["embedding_model_version"] == EMBEDDING_MODEL_VERSION
            assert chunk["embedding_dimensions"] == EMBEDDING_DIMENSIONS
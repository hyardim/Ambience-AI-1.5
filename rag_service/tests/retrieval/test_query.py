from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from src.retrieval.query import (
    EMBEDDING_MODEL_NAME,
    ProcessedQuery,
    RetrievalError,
    _expand_query,
    process_query,
)

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

MOCK_EMBEDDING = np.array([[0.1] * 384], dtype=np.float32)


def _make_mock_model(embedding: np.ndarray = MOCK_EMBEDDING) -> MagicMock:
    """Return a mock SentenceTransformer that returns a fixed embedding."""
    mock = MagicMock()
    mock.encode.return_value = embedding
    return mock


# -----------------------------------------------------------------------
# Tests — process_query()
# -----------------------------------------------------------------------


class TestProcessQuery:
    def test_returns_processed_query_pydantic_model(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment")
        assert isinstance(result, ProcessedQuery)

    def test_embedding_has_correct_dimensions(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment")
        assert len(result.embedding) == 384

    def test_empty_query_raises_value_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            process_query("")

    def test_whitespace_only_query_raises_value_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            process_query("   ")

    def test_expand_false_leaves_query_unchanged(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment", expand=False)
        assert result.expanded == result.original

    def test_expand_true_appends_synonyms(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment", expand=True)
        assert "urate" in result.expanded
        assert "hyperuricemia" in result.expanded
        assert "uric acid" in result.expanded

    def test_expand_true_preserves_original_terms(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment", expand=True)
        assert "gout" in result.expanded
        assert "treatment" in result.expanded

    def test_unknown_term_expansion_leaves_query_unchanged(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("fibromyalgia management", expand=True)
        assert result.expanded == "fibromyalgia management"

    def test_embedding_model_name_recorded_in_output(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment")
        assert result.embedding_model == EMBEDDING_MODEL_NAME

    def test_model_load_failure_raises_retrieval_error(self):
        with patch(
            "src.retrieval.query._load_model",
            side_effect=RuntimeError("model not found"),
        ):
            with pytest.raises(RetrievalError) as exc_info:
                process_query("gout treatment")
        assert exc_info.value.stage == "QUERY"

    def test_embedding_failure_raises_retrieval_error(self):
        mock_model = _make_mock_model()
        mock_model.encode.side_effect = RuntimeError("CUDA out of memory")
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            with pytest.raises(RetrievalError) as exc_info:
                process_query("gout treatment")
        assert exc_info.value.stage == "QUERY"

    def test_wrong_embedding_dimensions_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ProcessedQuery(
                original="test",
                expanded="test",
                embedding=[0.1] * 100,  # wrong dimensions
                embedding_model="some-model",
            )

    def test_query_exceeding_token_limit_raises_value_error(self):
        # ~400 words * 1.3 = ~520 estimated tokens, exceeds 512 limit
        long_query = " ".join(["gout"] * 400)
        with pytest.raises(ValueError, match="exceeds 512 token limit"):
            process_query(long_query)

    def test_model_loaded_once_across_multiple_calls(self):
        mock_model = _make_mock_model()
        with patch(
            "src.retrieval.query._load_model", return_value=mock_model
        ) as mock_load:
            process_query("gout treatment")
            process_query("ra management")
        assert mock_load.call_count == 2


# -----------------------------------------------------------------------
# Tests — _expand_query()
# -----------------------------------------------------------------------


class TestExpandQuery:
    def test_gout_expansion(self):
        result = _expand_query("gout")
        assert "urate" in result
        assert "hyperuricemia" in result
        assert "uric acid" in result

    def test_ra_expansion(self):
        result = _expand_query("RA treatment")
        assert "rheumatoid arthritis" in result

    def test_oa_expansion(self):
        result = _expand_query("OA management")
        assert "osteoarthritis" in result

    def test_no_duplicate_synonyms_added(self):
        result = _expand_query("gout urate management")
        assert result.count("urate") == 1

    def test_unknown_term_returns_original(self):
        query = "fibromyalgia management"
        result = _expand_query(query)
        assert result == query


# -----------------------------------------------------------------------
# Tests — RetrievalError
# -----------------------------------------------------------------------


class TestRetrievalError:
    def test_retrieval_error_has_stage(self):
        err = RetrievalError(stage="QUERY", query="test", message="something failed")
        assert err.stage == "QUERY"

    def test_retrieval_error_has_query(self):
        err = RetrievalError(stage="QUERY", query="test query", message="failed")
        assert err.query == "test query"

    def test_retrieval_error_str_includes_stage_and_query(self):
        err = RetrievalError(stage="QUERY", query="test", message="failed")
        assert "QUERY" in str(err)
        assert "test" in str(err)

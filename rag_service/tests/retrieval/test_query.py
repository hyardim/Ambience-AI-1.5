from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

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
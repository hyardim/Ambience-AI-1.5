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
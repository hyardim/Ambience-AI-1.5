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

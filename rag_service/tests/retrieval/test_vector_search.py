from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.query import RetrievalError
from src.retrieval.vector_search import VectorSearchResult, vector_search
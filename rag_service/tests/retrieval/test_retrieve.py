from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.citation import Citation, CitedResult
from src.retrieval.fusion import FusedResult
from src.retrieval.keyword_search import KeywordSearchResult
from src.retrieval.query import ProcessedQuery, RetrievalError
from src.retrieval.rerank import RankedResult
from src.retrieval.vector_search import VectorSearchResult

QUERY = "gout treatment options"
DB_URL = "postgresql://localhost/test"
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.retrieval.query import RetrievalError
from src.retrieval.keyword_search import KeywordSearchResult, keyword_search

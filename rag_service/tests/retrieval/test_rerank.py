from __future__ import annotations

from math import exp
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.fusion import FusedResult
from src.retrieval.query import RetrievalError
from src.retrieval.rerank import (
    RankedResult,
    _jaccard_similarity,
    deduplicate,
    rerank,
)


from __future__ import annotations

from math import exp
from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .fusion import FusedResult
from .query import RetrievalError

logger = setup_logger(__name__)

# Module-level model cache — loaded once on first call
_model = None
_model_name_loaded: str | None = None

LARGE_INPUT_WARNING_THRESHOLD = 50

# -----------------------------------------------------------------------
# Pydantic model
# -----------------------------------------------------------------------


class RankedResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    rerank_score: float
    rrf_score: float
    vector_score: float | None
    keyword_rank: float | None
    metadata: dict[str, Any]
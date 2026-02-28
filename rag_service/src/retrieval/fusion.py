from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .keyword_search import KeywordSearchResult
from .vector_search import VectorSearchResult

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Pydantic model
# -----------------------------------------------------------------------


class FusedResult(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    rrf_score: float
    vector_score: float | None
    keyword_rank: float | None
    metadata: dict[str, Any]

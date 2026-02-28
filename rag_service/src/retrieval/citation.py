from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .rerank import RankedResult

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------


class CitationError(Exception):
    def __init__(self, chunk_id: str, missing_field: str) -> None:
        self.chunk_id = chunk_id
        self.missing_field = missing_field
        super().__init__(
            f"Missing citation field '{missing_field}' for chunk {chunk_id}"
        )

from __future__ import annotations

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .fusion import FusedResult

logger = setup_logger(__name__)

VALID_CONTENT_TYPES = {"text", "table"}

# -----------------------------------------------------------------------
# Config model
# -----------------------------------------------------------------------


class FilterConfig(BaseModel):
    specialty: str | None = None
    source_name: str | None = None
    doc_type: str | None = None
    score_threshold: float = 0.3
    content_types: list[str] | None = None  # None = all, e.g. ["text", "table"]

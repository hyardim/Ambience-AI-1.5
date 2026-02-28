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


# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def apply_filters(
    results: list[FusedResult],
    config: FilterConfig,
) -> list[FusedResult]:
    """
    Apply post-fusion metadata filters and score thresholding.

    Acts as a quality gate before reranking — drops results that are
    out of scope or below the minimum similarity threshold.

    Filters are ANDed together. RRF ordering from fusion is preserved.

    Args:
        results: Fused results from reciprocal_rank_fusion()
        config: Filter configuration

    Returns:
        Filtered list of FusedResult in original RRF score order

    Raises:
        ValueError: If score_threshold is outside [0, 1] or content_types
                    contains invalid values
    """
    pass
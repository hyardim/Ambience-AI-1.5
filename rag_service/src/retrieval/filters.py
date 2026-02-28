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


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _validate_config(config: FilterConfig) -> None:
    """Raise ValueError for invalid FilterConfig values."""
    if config.score_threshold < 0 or config.score_threshold > 1:
        raise ValueError(
            f"score_threshold must be between 0 and 1, "
            f"got {config.score_threshold!r}"
        )
    if config.content_types is not None:
        invalid = set(config.content_types) - VALID_CONTENT_TYPES
        if invalid:
            raise ValueError(
                f"Invalid content_type(s): {invalid}. "
                f"Must be one of {VALID_CONTENT_TYPES}"
            )

def _passes_metadata_filters(result: FusedResult, config: FilterConfig) -> bool:
    """Return True if result passes all metadata filters."""
    meta = result.metadata

    if config.specialty is not None and meta.get("specialty") != config.specialty:
        return False

    if (
        config.source_name is not None
        and meta.get("source_name") != config.source_name
    ):
        return False

    if config.doc_type is not None and meta.get("doc_type") != config.doc_type:
        return False

    if config.content_types is not None:
        if meta.get("content_type") not in config.content_types:
            return False

    return True
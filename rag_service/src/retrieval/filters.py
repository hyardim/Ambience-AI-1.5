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

    _validate_config(config)

    if not results:
        return []

    logger.debug(
        f"Applying filters: specialty={config.specialty}, "
        f"source_name={config.source_name}, "
        f"doc_type={config.doc_type}, "
        f"content_types={config.content_types}, "
        f"threshold={config.score_threshold}"
    )

    # Score threshold pass
    after_threshold = []
    threshold_dropped = 0
    for result in results:
        if (
            result.vector_score is not None
            and result.vector_score < config.score_threshold
        ):
            threshold_dropped += 1
        else:
            after_threshold.append(result)

    if threshold_dropped:
        logger.debug(f"Dropped {threshold_dropped} results below score threshold")

    # Metadata filter pass
    after_metadata = []
    metadata_dropped = 0
    for result in after_threshold:
        if _passes_metadata_filters(result, config):
            after_metadata.append(result)
        else:
            metadata_dropped += 1

    if metadata_dropped:
        logger.debug(f"Dropped {metadata_dropped} results by metadata filter")

    if not after_metadata:
        logger.warning(
            "All results removed by filters — consider lowering score_threshold "
            "or relaxing metadata filters"
        )
        return []

    logger.debug(f"{len(after_metadata)} results remaining after filtering")

    return after_metadata


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _validate_config(config: FilterConfig) -> None:
    """Raise ValueError for invalid FilterConfig values."""
    if config.score_threshold < 0 or config.score_threshold > 1:
        raise ValueError(
            f"score_threshold must be between 0 and 1, got {config.score_threshold!r}"
        )
    if config.content_types is not None:
        invalid = set(config.content_types) - VALID_CONTENT_TYPES
        if invalid:
            raise ValueError(
                f"Invalid content_type(s): {sorted(invalid)}. "
                f"Must be one of {sorted(VALID_CONTENT_TYPES)}"
            )


def _passes_metadata_filters(result: FusedResult, config: FilterConfig) -> bool:
    """Return True if result passes all metadata filters."""
    meta = result.metadata

    if config.specialty is not None and meta.get("specialty") != config.specialty:
        return False

    if config.source_name is not None and meta.get("source_name") != config.source_name:
        return False

    if config.doc_type is not None and meta.get("doc_type") != config.doc_type:
        return False

    if config.content_types is not None:
        if meta.get("content_type") not in config.content_types:
            return False

    return True

from __future__ import annotations

import time
from dataclasses import dataclass

from sentence_transformers import SentenceTransformer

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
MAX_TOKENS = 512

# Simple rule-based expansion dictionary for medical terminology
EXPANSION_DICT: dict[str, list[str]] = {
    "gout": ["urate", "hyperuricemia", "uric acid"],
    "ra": ["rheumatoid arthritis"],
    "oa": ["osteoarthritis"],
    "sle": ["systemic lupus erythematosus", "lupus"],
    "as": ["ankylosing spondylitis"],
    "psa": ["psoriatic arthritis"],
    "ms": ["multiple sclerosis"],
    "dmard": ["disease modifying antirheumatic drug"],
    "nsaid": ["non-steroidal anti-inflammatory", "anti-inflammatory"],
    "methotrexate": ["mtx", "disease modifying antirheumatic drug"],
}

# -----------------------------------------------------------------------
# Model — loaded once at module level
# -----------------------------------------------------------------------

_MODEL: SentenceTransformer | None = None


def _load_model() -> SentenceTransformer:
    """Load and return the embedding model. Cached after first call."""
    global _MODEL
    if _MODEL is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _MODEL

# -----------------------------------------------------------------------
# Dataclass
# -----------------------------------------------------------------------

@dataclass
class ProcessedQuery:
    original: str
    expanded: str           # same as original if expansion disabled
    embedding: list[float]  # 384-dimensional vector
    embedding_model: str

# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def process_query(
    query: str,
    expand: bool = False,
) -> ProcessedQuery:
    """
    Process a raw query string into an embedding vector.

    Args:
        query: Raw natural language query string
        expand: Whether to apply rule-based medical term expansion

    Returns:
        ProcessedQuery with original, expanded, embedding, and model name

    Raises:
        ValueError: If query is empty, whitespace only, or exceeds 512 tokens
        RetrievalError: If model fails to load or embedding fails
    """
    pass

# -----------------------------------------------------------------------
# RetrievalError — defined here to avoid circular imports.
# All other stage files import it from here or from retrieve.py
# -----------------------------------------------------------------------

class RetrievalError(Exception):
    """Raised when a retrieval pipeline stage fails."""

    def __init__(self, stage: str, query: str, message: str) -> None:
        self.stage = stage
        self.query = query
        self.message = message
        super().__init__(f"{stage} | {query} | {message}")
from __future__ import annotations

import time
from typing import Any

from sentence_transformers import SentenceTransformer

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_VERSION = "main"
EMBEDDING_DIMENSIONS = 384
EMBEDDING_BATCH_SIZE = 32
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds, doubled each retry

# -----------------------------------------------------------------------
# Model — loaded once at module level
# -----------------------------------------------------------------------

_MODEL: SentenceTransformer | None = None


def _load_model() -> SentenceTransformer:
    """Load and return the embedding model. Called once at module level."""
    global _MODEL
    if _MODEL is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _MODEL

# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def embed_chunks(chunked_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Generate embeddings for all chunks in a ChunkedDocument.

    Args:
        chunked_doc: ChunkedDocument dict from chunk.py

    Returns:
        EmbeddedDocument with embedding fields attached to every chunk

    Processing steps:
        1. Extract texts from all chunks
        2. Split into batches of EMBEDDING_BATCH_SIZE
        3. Embed each batch with retry + exponential backoff
        4. On batch failure, fall back to per-chunk embedding
        5. On chunk failure, quarantine with embedding_status="failed"
        6. Attach embedding metadata to all chunks
    """
    pass
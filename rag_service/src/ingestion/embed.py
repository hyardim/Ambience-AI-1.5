from __future__ import annotations

import math
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
    chunks = chunked_doc.get("chunks", [])

    if not chunks:
        logger.info("No chunks to embed.")
        return {**chunked_doc, "chunks": chunks}

    model = _load_model()
    logger.info(f"Embedding {len(chunks)} chunks in batches of {EMBEDDING_BATCH_SIZE}")

    n_success = 0
    n_failed = 0

    for batch_start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
        batch_num = batch_start // EMBEDDING_BATCH_SIZE + 1
        texts = [c.get("text", "") for c in batch]

        try:
            vectors = _embed_batch(model, texts)
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.update(_make_success_fields(vector))
                n_success += 1
        except Exception:
            # Batch failed after all retries — fall back to per-chunk
            logger.warning(
                f"Batch {batch_num} failed after all retries, "
                f"falling back to per-chunk embedding"
            )
            for chunk in batch:
                text = chunk.get("text", "")
                single_vector, error = _embed_single(model, text)
                if single_vector is not None:
                    chunk.update(_make_success_fields(single_vector))
                    n_success += 1
                else:
                    chunk.update(
                        _make_failure_fields(error or "Failed after all retries")
                    )
                    n_failed += 1
                    logger.error(
                        f"Chunk {chunk.get('chunk_id')} failed after all retries"
                    )

    logger.info(f"Embedded: {n_success} success, {n_failed} failed")

    if n_success > 0:
        sample = chunks[0].get("embedding", [])
        if sample:
            norm = math.sqrt(sum(x * x for x in sample))
            logger.debug(f"Sample embedding norm: {norm:.4f}")

    return {**chunked_doc, "chunks": chunks}


# -----------------------------------------------------------------------
# Batch + single embedding with retry
# -----------------------------------------------------------------------


def _embed_batch(
    model: SentenceTransformer,
    texts: list[str],
    attempt: int = 0,
) -> list[list[float]]:
    """
    Embed a batch of texts with retry logic.

    Args:
        model: Loaded SentenceTransformer model
        texts: List of texts to embed
        attempt: Current attempt number (0-indexed)

    Returns:
        List of normalised embedding vectors

    Raises:
        Exception: On final failure so caller can fall back to per-chunk
    """
    try:
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]
    except Exception as e:
        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BACKOFF_BASE**attempt
            logger.warning(
                f"Batch embedding failed (attempt {attempt + 1}): {e}. "
                f"Retrying in {wait:.1f}s"
            )
            time.sleep(wait)
            return _embed_batch(model, texts, attempt + 1)
        raise


def _embed_single(
    model: SentenceTransformer,
    text: str,
    attempt: int = 0,
) -> tuple[list[float] | None, str | None]:
    """
    Embed a single text with retry + backoff.

    Returns:
        (normalised embedding, error_message) — error_message is None on success
    """
    try:
        vector = model.encode(
            [text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector[0].tolist(), None
    except Exception as e:
        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BACKOFF_BASE**attempt
            logger.warning(
                f"Single embedding failed (attempt {attempt + 1}): {e}. "
                f"Retrying in {wait:.1f}s"
            )
            time.sleep(wait)
            return _embed_single(model, text, attempt + 1)
        return None, str(e)


# -----------------------------------------------------------------------
# Metadata helpers
# -----------------------------------------------------------------------


def _make_success_fields(embedding: list[float]) -> dict[str, Any]:
    """Return embedding metadata dict for a successful embed."""
    return {
        "embedding": embedding,
        "embedding_status": "success",
        "embedding_model_name": EMBEDDING_MODEL_NAME,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "embedding_error": None,
    }


def _make_failure_fields(error: str) -> dict[str, Any]:
    """Return embedding metadata dict for a failed embed."""
    return {
        "embedding": None,
        "embedding_status": "failed",
        "embedding_model_name": EMBEDDING_MODEL_NAME,
        "embedding_model_version": EMBEDDING_MODEL_VERSION,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "embedding_error": error,
    }

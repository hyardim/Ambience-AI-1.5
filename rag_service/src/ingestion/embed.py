from __future__ import annotations

import math
import time
from typing import Any

from sentence_transformers import SentenceTransformer

from ..config import embed_config
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = f"sentence-transformers/{embed_config.embedding_model}"
EMBEDDING_MODEL_VERSION = "main"
EMBEDDING_DIMENSIONS = embed_config.embedding_dimension
EMBEDDING_BATCH_SIZE = 32
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds, doubled each retry

# -----------------------------------------------------------------------
# Model cache, keyed by model name
# -----------------------------------------------------------------------

_MODELS: dict[str, SentenceTransformer] = {}


def _load_model(model_name: str = EMBEDDING_MODEL_NAME) -> SentenceTransformer:
    """Load and cache embedding models by name."""
    if model_name not in _MODELS:
        logger.info(f"Loading embedding model: {model_name}")
        _MODELS[model_name] = SentenceTransformer(model_name)
    return _MODELS[model_name]


def load_embedder(model_name: str = EMBEDDING_MODEL_NAME) -> SentenceTransformer:
    """Public accessor for the shared embedding model."""
    return _load_model(model_name)


def get_vector_dim(model: SentenceTransformer) -> int:
    """Return embedding dimensionality for the provided model."""
    dimension = model.get_sentence_embedding_dimension()
    if dimension is None:
        raise ValueError("Embedding model did not report a vector dimension")
    return int(dimension)


# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def _embedding_text(chunk: dict[str, Any]) -> str:
    """Build the text string that gets embedded for a chunk.

    Prepends the section path and document title so that the vector
    embedding captures section-level context — not just the raw text.
    This helps semantic search distinguish chunks from different guideline
    sections that share body-part terminology.

    Page metadata is *not* included because it has no semantic value.
    """
    parts: list[str] = []
    citation = chunk.get("citation", {})
    title = citation.get("title", "")
    if title:
        parts.append(title)

    section_path = chunk.get("section_path") or []
    if isinstance(section_path, list) and section_path:
        parts.append(" > ".join(str(s) for s in section_path))
    elif chunk.get("section_title"):
        parts.append(str(chunk["section_title"]))

    text = str(chunk.get("text", ""))
    if parts:
        return f"[{' — '.join(parts)}] {text}"
    return text


def _resolve_embedding_settings(config: dict[str, Any] | None) -> dict[str, Any]:
    settings = config or {}
    return {
        "model_name": settings.get("model_name", EMBEDDING_MODEL_NAME),
        "model_version": settings.get("model_version", EMBEDDING_MODEL_VERSION),
        "dimensions": int(settings.get("dimensions", EMBEDDING_DIMENSIONS)),
        "batch_size": int(settings.get("batch_size", EMBEDDING_BATCH_SIZE)),
    }


def embed_chunks(
    chunked_doc: dict[str, Any],
    embedding_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
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

    settings = _resolve_embedding_settings(embedding_config)
    model = _load_model(settings["model_name"])
    batch_size = settings["batch_size"]
    logger.info(f"Embedding {len(chunks)} chunks in batches of {batch_size}")

    n_success = 0
    n_failed = 0

    for batch_start in range(0, len(chunks), batch_size):
        batch = chunks[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        texts = [_embedding_text(c) for c in batch]

        try:
            vectors = _embed_batch(model, texts)
            for chunk, vector in zip(batch, vectors, strict=True):
                chunk.update(
                    _make_success_fields(
                        vector,
                        model_name=settings["model_name"],
                        model_version=settings["model_version"],
                        dimensions=settings["dimensions"],
                    )
                )
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
                    chunk.update(
                        _make_success_fields(
                            single_vector,
                            model_name=settings["model_name"],
                            model_version=settings["model_version"],
                            dimensions=settings["dimensions"],
                        )
                    )
                    n_success += 1
                else:
                    chunk.update(
                        _make_failure_fields(
                            error or "Failed after all retries",
                            model_name=settings["model_name"],
                            model_version=settings["model_version"],
                            dimensions=settings["dimensions"],
                        )
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


def _make_success_fields(
    embedding: list[float],
    *,
    model_name: str = EMBEDDING_MODEL_NAME,
    model_version: str = EMBEDDING_MODEL_VERSION,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> dict[str, Any]:
    """Return embedding metadata dict for a successful embed."""
    return {
        "embedding": embedding,
        "embedding_status": "success",
        "embedding_model_name": model_name,
        "embedding_model_version": model_version,
        "embedding_dimensions": dimensions,
        "embedding_error": None,
    }


def _make_failure_fields(
    error: str,
    *,
    model_name: str = EMBEDDING_MODEL_NAME,
    model_version: str = EMBEDDING_MODEL_VERSION,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> dict[str, Any]:
    """Return embedding metadata dict for a failed embed."""
    return {
        "embedding": None,
        "embedding_status": "failed",
        "embedding_model_name": model_name,
        "embedding_model_version": model_version,
        "embedding_dimensions": dimensions,
        "embedding_error": error,
    }

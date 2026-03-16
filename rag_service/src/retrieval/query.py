from __future__ import annotations

import time
from typing import Any, Protocol, cast

import tiktoken
from pydantic import BaseModel, Field

from ..config import embed_config
from ..ingestion.embed import load_embedder
from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = f"sentence-transformers/{embed_config.embedding_model}"
EMBEDDING_DIMENSIONS = embed_config.embedding_dimension
_ENCODER = tiktoken.get_encoding("cl100k_base")

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
    "gca": ["giant cell arteritis", "temporal arteritis"],
    "pmr": ["polymyalgia rheumatica"],
    "tnf": ["tumor necrosis factor"],
    "csf": ["cerebrospinal fluid"],
    "mri": ["magnetic resonance imaging"],
    "ct": ["computed tomography"],
    "edss": ["expanded disability status scale"],
    "rrms": ["relapsing remitting multiple sclerosis"],
    "spms": ["secondary progressive multiple sclerosis"],
    "ppms": ["primary progressive multiple sclerosis"],
    "cis": ["clinically isolated syndrome"],
    "dmt": ["disease modifying therapy"],
}


def _load_model() -> object:
    """Load and return the shared embedding model."""
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
    return load_embedder(model_name=EMBEDDING_MODEL_NAME)


class _EmbeddingModel(Protocol):
    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> object: ...


# -----------------------------------------------------------------------
# Processed Query Model
# -----------------------------------------------------------------------


class ProcessedQuery(BaseModel):
    original: str
    expanded: str
    embedding: list[float] = Field(
        min_length=EMBEDDING_DIMENSIONS, max_length=EMBEDDING_DIMENSIONS
    )
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
        RetrievalError: If model fails to load, embedding fails, or
            ProcessedQuery construction fails
    """
    if not query or not query.strip():
        raise ValueError("Query must not be empty")

    _validate_token_length(query)

    logger.debug(f'Processing query: "{query}"')

    expanded = _expand_query(query) if expand else query
    if expand and expanded != query:
        logger.debug(f'Query expanded: "{expanded}"')
        _validate_token_length(expanded)  # validate again after expansion

    try:
        model = _load_model()
    except Exception as e:
        raise RetrievalError(
            stage="QUERY",
            query=query,
            message=f"Failed to load embedding model: {e}",
        ) from e

    try:
        start = time.perf_counter()
        embedding = _embed(model, expanded)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(
            f"Embedding complete in {elapsed_ms:.0f}ms, dimensions={len(embedding)}"
        )
    except Exception as e:
        raise RetrievalError(
            stage="QUERY",
            query=query,
            message=f"Failed to embed query: {e}",
        ) from e

    try:
        return ProcessedQuery(
            original=query,
            expanded=expanded,
            embedding=embedding,
            embedding_model=EMBEDDING_MODEL_NAME,
        )
    except Exception as e:
        raise RetrievalError(
            stage="QUERY",
            query=query,
            message=f"Failed to construct ProcessedQuery: {e}",
        ) from e


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _validate_token_length(query: str) -> None:
    """Raise ValueError if query exceeds MAX_TOKENS tokens."""
    max_tokens = embed_config.query_max_tokens
    token_count = len(_ENCODER.encode(query))
    if token_count > max_tokens:
        raise ValueError(
            f"Query exceeds {max_tokens} token limit "
            f"({token_count} tokens)"
        )


def _expand_query(query: str) -> str:
    """Apply rule-based medical term expansion to query.

    Checks each word against EXPANSION_DICT (case-insensitive).
    Appends synonyms for any matched terms. Original terms always preserved.
    """
    words = query.lower().split()
    query_lower = query.lower()
    additions: list[str] = []
    added: set[str] = set()

    for word in words:
        clean_word = word.rstrip(".,;:?!")
        if clean_word in EXPANSION_DICT:
            for synonym in EXPANSION_DICT[clean_word]:
                synonym_lower = synonym.lower()
                if synonym_lower not in query_lower and synonym_lower not in added:
                    additions.append(synonym)
                    added.add(synonym_lower)

    if not additions:
        return query

    return query + " " + " ".join(additions)


def _embed(model: object, text: str) -> list[float]:
    """Embed text and return normalised float vector.

    Normalisation required for cosine similarity to work correctly
    with pgvector's <=> operator.
    """
    encoder = cast(_EmbeddingModel, model)
    vector = cast(
        Any,
        encoder.encode([text], normalize_embeddings=True, show_progress_bar=False),
    )
    return cast(list[float], vector[0].tolist())


# -----------------------------------------------------------------------
# RetrievalError — defined here to avoid circular imports.
# All other retrieval stage files import it from this module.
# -----------------------------------------------------------------------


class RetrievalError(Exception):
    """Raised when a retrieval pipeline stage fails."""

    def __init__(self, stage: str, query: str, message: str) -> None:
        self.stage = stage
        self.query = query
        self.message = message
        super().__init__(f"{stage} | {query} | {message}")

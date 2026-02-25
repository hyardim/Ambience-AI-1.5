from __future__ import annotations

import math
import time

from pydantic import BaseModel, Field
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
# Processed Query Model
# -----------------------------------------------------------------------


class ProcessedQuery(BaseModel):
    original: str
    expanded: str
    embedding: list[float] = Field(min_length=384, max_length=384)
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
    if not query or not query.strip():
        raise ValueError("Query must not be empty")

    _validate_token_length(query)

    logger.debug(f'Processing query: "{query}"')

    expanded = _expand_query(query) if expand else query
    if expand and expanded != query:
        logger.debug(f'Query expanded: "{expanded}"')
        _validate_token_length(query)  # validate again after expansion

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

    return ProcessedQuery(
        original=query,
        expanded=expanded,
        embedding=embedding,
        embedding_model=EMBEDDING_MODEL_NAME,
    )


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _validate_token_length(query: str) -> None:
    """Raise ValueError if query exceeds MAX_TOKENS tokens."""
    word_count = len(query.split())
    estimated_tokens = math.ceil(word_count * 1.3)
    if estimated_tokens > MAX_TOKENS:
        raise ValueError(
            f"Query exceeds {MAX_TOKENS} token limit "
            f"(estimated {estimated_tokens} tokens)"
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


def _embed(model: SentenceTransformer, text: str) -> list[float]:
    """Embed text and return normalised float vector.

    Normalisation required for cosine similarity to work correctly
    with pgvector's <=> operator.
    """
    vector = model.encode([text], normalize_embeddings=True, show_progress_bar=False)
    return vector[0].tolist()


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

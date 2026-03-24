from __future__ import annotations

import re
import time
from typing import Any, Protocol, cast

from pydantic import BaseModel, Field

from ..config import embed_config
from ..ingestion.embed import load_embedder
from ..utils.logger import setup_logger
from ..utils.tokenizer import count_tokens

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = f"sentence-transformers/{embed_config.embedding_model}"
EMBEDDING_DIMENSIONS = embed_config.embedding_dimension

# Simple rule-based expansion dictionary for medical terminology
EXPANSION_DICT: dict[str, list[str]] = {
    "aspirin": ["acetylsalicylic acid", "asa"],
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
    "neutropenia": ["low neutrophils", "drug toxicity", "bone marrow suppression"],
    "gca": ["giant cell arteritis", "temporal arteritis"],
    "pmr": ["polymyalgia rheumatica"],
    "proteinuria": ["renal involvement", "kidney disease", "nephritis"],
    "creatinine": ["renal impairment", "kidney dysfunction"],
    "tnf": ["tumor necrosis factor"],
    "csf": ["cerebrospinal fluid"],
    "mri": ["magnetic resonance imaging"],
    "ct": ["computed tomography"],
    "tremor": ["essential tremor", "parkinsonian tremor"],
    "edss": ["expanded disability status scale"],
    "rrms": ["relapsing remitting multiple sclerosis"],
    "spms": ["secondary progressive multiple sclerosis"],
    "ppms": ["primary progressive multiple sclerosis"],
    "cis": ["clinically isolated syndrome"],
    "dmt": ["disease modifying therapy"],
}

RED_FLAG_PATTERNS: tuple[tuple[tuple[str, ...], list[str]], ...] = (
    (
        (
            r"\b(methotrexate|mtx)\b",
            r"\b(fever|pyrexia)\b",
            r"\b(sore throat|pharyngitis|neutropenia|low neutrophils)\b",
        ),
        [
            "DMARD toxicity",
            "drug-induced neutropenia",
            "urgent blood count review",
            "csDMARD monitoring",
        ],
    ),
    (
        (
            r"\b(sle|systemic lupus erythematosus|lupus)\b",
            r"\b(proteinuria|albuminuria)\b",
            r"\b(creatinine|renal impairment|kidney dysfunction)\b",
        ),
        [
            "lupus nephritis",
            "renal involvement",
            "nephrology referral",
            "urgent specialist assessment",
        ],
    ),
    (
        (
            r"\b(joint swelling|synovitis|swollen joints)\b",
            r"\b(knees?|wrists?)\b",
            r"\b(referral|referred|specialist)\b",
        ),
        [
            "early inflammatory arthritis",
            "baseline blood tests",
            "plain radiographs",
            "rheumatology triage",
        ],
    ),
    (
        (
            r"\bback pain\b",
            (
                r"\b(urinary retention|urinary incontinence|bladder dysfunction|"
                r"bowel dysfunction)\b"
            ),
            (
                r"\b(bilateral leg weakness|leg weakness|progressive "
                r"neurological deficit|saddle anaesthesia)\b"
            ),
        ),
        [
            "cauda equina syndrome",
            "progressive neurological deficit",
            "spinal emergency",
            "sciatica",
        ],
    ),
    (
        (
            r"\b(gait disturbance|gait apraxia|walking difficulty)\b",
            r"\b(urinary incontinence|urinary urgency)\b",
            r"\b(ventriculomegaly|hydrocephalus)\b",
        ),
        [
            "normal pressure hydrocephalus",
            "NPH",
            "gait apraxia",
        ],
    ),
    (
        (
            r"\b(transient visual disturbance|visual disturbance)\b",
            r"\bheadache\b",
            r"\b(transient|lasting)\b",
        ),
        [
            "migraine aura",
            "TIA",
            "transient ischaemic attack",
        ],
    ),
)


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
    token_count = count_tokens(query)
    if token_count > max_tokens:
        raise ValueError(
            f"Query exceeds {max_tokens} token limit ({token_count} tokens)"
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
        query_with_red_flags = _expand_red_flag_patterns(query, query_lower)
        return query_with_red_flags

    expanded = query + " " + " ".join(additions)
    return _expand_red_flag_patterns(expanded, expanded.lower())


def _expand_red_flag_patterns(query: str, query_lower: str) -> str:
    additions: list[str] = []
    for patterns, synonyms in RED_FLAG_PATTERNS:
        if all(re.search(pattern, query_lower) for pattern in patterns):
            for synonym in synonyms:
                synonym_lower = synonym.lower()
                if synonym_lower not in query_lower and synonym_lower not in additions:
                    additions.append(synonym)
    if not additions:
        return query
    return query + " " + " ".join(additions)


def expand_query_text(query: str) -> str:
    """Return the rule-based expanded query text without embedding it."""
    return _expand_query(query)


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

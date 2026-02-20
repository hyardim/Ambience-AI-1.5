import hashlib
from typing import Dict, List

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import MODEL_NAME


def load_embedder() -> SentenceTransformer:
    """Load and return the SentenceTransformer model."""
    return SentenceTransformer(MODEL_NAME)


def text_sha256(text: str) -> str:
    """SHA-256 hash for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_chunks(model: SentenceTransformer, chunks: List[Dict], batch_size: int = 64) -> List[Dict]:
    """Attach embeddings and text hashes to each chunk dict."""
    if not chunks:
        return chunks

    texts = [c["text"] for c in chunks]
    embs = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    for i, c in enumerate(chunks):
        c["text_hash"] = text_sha256(c["text"])
        c["embedding"] = embs[i].tolist()

    return chunks


def get_vector_dim(model: SentenceTransformer) -> int:
    """Return embedding dimension for the model."""
    v = model.encode(["dimension_check"], convert_to_numpy=True)
    return int(v.shape[1])

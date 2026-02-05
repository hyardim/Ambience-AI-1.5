# src/embed.py

# Import hashing for stable IDs.
import hashlib

# Import typing.
from typing import List, Dict

# Import numpy for arrays.
import numpy as np

# Import SentenceTransformer for embeddings.
from sentence_transformers import SentenceTransformer

# Import config model name.
from .config import MODEL_NAME

def load_embedder() -> SentenceTransformer:
    """
    Loads and returns the SentenceTransformer model.
    """
    return SentenceTransformer(MODEL_NAME)

def text_sha256(text: str) -> str:
    """
    Returns a SHA-256 hash of a text chunk for deduping.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def embed_chunks(model: SentenceTransformer, chunks: List[Dict], batch_size: int = 64) -> List[Dict]:
    """
    Adds 'embedding' and 'text_hash' to each chunk dict.
    """
    if not chunks:
        return chunks

    # Collect texts.
    texts = [c["text"] for c in chunks]

    # Compute embeddings (numpy arrays).
    embs = model.encode(texts, batch_size=batch_size, show_progress_bar=True, convert_to_numpy=True, normalize_embeddings=True)

    # Attach embedding + text_hash.
    for i, c in enumerate(chunks):
        c["text_hash"] = text_sha256(c["text"])
        # Convert numpy vector to python list for psycopg2 insertion into pgvector.
        c["embedding"] = embs[i].tolist()

    return chunks

def get_vector_dim(model: SentenceTransformer) -> int:
    """
    Returns embedding dimension for the model.
    """
    # Embed a trivial string and read the length.
    v = model.encode(["dimension_check"], convert_to_numpy=True)
    return int(v.shape[1])

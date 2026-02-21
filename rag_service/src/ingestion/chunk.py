from __future__ import annotations

import hashlib
from typing import Any

import nltk
import tiktoken

from ..utils.logger import setup_logger

nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)
from nltk.tokenize import sent_tokenize  # noqa: E402

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

MIN_CHUNK_TOKENS = 300
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 80
SHORT_SECTION_TOKENS = 150
MAX_MERGE_SECTIONS = 2

_ENCODER = tiktoken.get_encoding("cl100k_base")

# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def chunk_document(metadata_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Split a MetadataDocument into citation-safe chunks.

    Args:
        metadata_doc: MetadataDocument dict from metadata.py

    Returns:
        ChunkedDocument with 'chunks' list added

    Processing steps:
        1. Filter blocks to include_in_chunks=True only
        2. Separate table blocks → one chunk each
        3. Group text blocks by section_path
        4. Merge very short sections (< SHORT_SECTION_TOKENS)
        5. Split each section group into sentence-aligned chunks
        6. Apply overlap between consecutive text chunks
        7. Clean chunk text
        8. Attach full chunk metadata and citation
        9. Assign chunk_index and generate chunk_id
    """
    pass


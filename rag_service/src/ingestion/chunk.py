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

# -----------------------------------------------------------------------
# Token counting + sentence splitting
# -----------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return len(_ENCODER.encode(text))


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using nltk.sent_tokenize."""
    sentences = sent_tokenize(text)
    return [s for s in sentences if s.strip()]

# -----------------------------------------------------------------------
# Table chunks
# -----------------------------------------------------------------------


def make_table_chunk(
    block: dict[str, Any],
    doc_meta: dict[str, Any],
    chunk_index: int,
) -> dict[str, Any]:
    """Create a single chunk from a table block."""
    text = clean_chunk_text(block.get("text", ""))
    page = block.get("page_number", 0)
    section_path = block.get("section_path", ["Unknown"])
    section_title = block.get("section_title", "Unknown")
    page_range = str(page)

    citation = build_citation(
        {
            "section_path": section_path,
            "section_title": section_title,
            "page_range": page_range,
        },
        doc_meta,
    )

    return {
        "chunk_id": generate_chunk_id(
            doc_meta.get("doc_id", ""),
            doc_meta.get("doc_version", ""),
            text,
        ),
        "chunk_index": chunk_index,
        "content_type": "table",
        "text": text,
        "section_path": section_path,
        "section_title": section_title,
        "page_start": page,
        "page_end": page,
        "block_uids": [block.get("block_uid", "")],
        "token_count": count_tokens(text),
        "citation": citation,
    }

# -----------------------------------------------------------------------
# Section grouping + merging
# -----------------------------------------------------------------------


def group_blocks_by_section(
    blocks: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group consecutive text blocks by identical section_path."""
    if not blocks:
        return []

    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = [blocks[0]]
    current_path = tuple(blocks[0].get("section_path", []))

    for block in blocks[1:]:
        path = tuple(block.get("section_path", []))
        if path == current_path:
            current_group.append(block)
        else:
            groups.append(current_group)
            current_group = [block]
            current_path = path

    groups.append(current_group)
    return groups


# -----------------------------------------------------------------------
# Citation + chunk ID
# -----------------------------------------------------------------------


def build_citation(
    chunk_meta: dict[str, Any],
    doc_meta: dict[str, Any],
) -> dict[str, Any]:
    """Build citation object from chunk and document metadata."""
    return {
        "doc_id": doc_meta.get("doc_id", ""),
        "source_name": doc_meta.get("source_name", ""),
        "specialty": doc_meta.get("specialty", ""),
        "title": doc_meta.get("title", ""),
        "author_org": doc_meta.get("author_org", ""),
        "creation_date": doc_meta.get("creation_date", ""),
        "last_updated_date": doc_meta.get("last_updated_date", ""),
        "section_path": chunk_meta.get("section_path", []),
        "section_title": chunk_meta.get("section_title", ""),
        "page_range": chunk_meta.get("page_range", ""),
        "source_url": doc_meta.get("source_url", ""),
        "access_date": doc_meta.get("ingestion_date", ""),
    }

def generate_chunk_id(doc_id: str, doc_version: str, text: str) -> str:
    """Stable chunk ID: SHA-256 of doc_id + doc_version + text."""
    hash_input = f"{doc_id}|{doc_version}|{text}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

# -----------------------------------------------------------------------
# Text cleaning
# -----------------------------------------------------------------------

def clean_chunk_text(text: str) -> str:
    """Strip whitespace, collapse excessive newlines, preserve paragraph breaks."""
    import re
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

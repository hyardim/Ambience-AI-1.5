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

def merge_short_sections(
    groups: list[list[dict[str, Any]]],
) -> list[list[dict[str, Any]]]:
    """Merge section groups below SHORT_SECTION_TOKENS into next valid group."""
    if not groups:
        return []

    result: list[list[dict[str, Any]]] = []
    i = 0

    while i < len(groups):
        group = groups[i]
        group_text = " ".join(b.get("text", "") for b in group)
        group_tokens = count_tokens(group_text)

        if group_tokens < SHORT_SECTION_TOKENS:
            merged = list(group)
            merges = 0
            j = i + 1

            while j < len(groups) and merges < MAX_MERGE_SECTIONS:
                next_group = groups[j]
                if any(b.get("content_type") == "table" for b in next_group):
                    break
                merged.extend(next_group)
                merges += 1
                j += 1

                merged_text = " ".join(b.get("text", "") for b in merged)
                if count_tokens(merged_text) >= SHORT_SECTION_TOKENS:
                    break

            result.append(merged)
            i = j if merges > 0 else i + 1
        else:
            result.append(group)
            i += 1

    return result

# -----------------------------------------------------------------------
# Text chunking
# -----------------------------------------------------------------------

def _build_text_chunk(
    sentences: list[str],
    contributing_blocks: list[dict[str, Any]],
    doc_meta: dict[str, Any],
    chunk_index: int,
) -> dict[str, Any] | None:
    """Build a text chunk dict from sentences and contributing blocks."""
    text = clean_chunk_text(" ".join(sentences))
    if not text or not contributing_blocks:
        return None

    page_numbers = [b.get("page_number", 0) for b in contributing_blocks]
    page_start = min(page_numbers)
    page_end = max(page_numbers)
    page_range = str(page_start) if page_start == page_end else f"{page_start}-{page_end}"

    section_path = contributing_blocks[0].get("section_path", ["Unknown"])
    section_title = contributing_blocks[0].get("section_title", "Unknown")

    block_uids = list(dict.fromkeys(
        b.get("block_uid", "") for b in contributing_blocks
        if b.get("block_uid")
    ))

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
        "content_type": "text",
        "text": text,
        "section_path": section_path,
        "section_title": section_title,
        "page_start": page_start,
        "page_end": page_end,
        "block_uids": block_uids,
        "token_count": count_tokens(text),
        "citation": citation,
    }

def _compute_overlap(sentences: list[str]) -> list[str]:
    """Take sentences from end of list until overlap token budget is reached."""
    overlap: list[str] = []
    for sentence in reversed(sentences):
        candidate = [sentence] + overlap
        if count_tokens(" ".join(candidate)) > OVERLAP_TOKENS:
            break
        overlap = candidate
    return overlap


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

from __future__ import annotations

import hashlib
import re
from typing import Any

import nltk
from nltk.tokenize import sent_tokenize

from ..utils.logger import setup_logger
from ..utils.tokenizer import count_tokens as shared_count_tokens

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

# Aspirational minimum — not enforced when section boundaries prevent merging.
MIN_CHUNK_TOKENS = 300
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 80
SHORT_SECTION_TOKENS = 150
MAX_MERGE_SECTIONS = 2

_NLTK_INITIALISED = False


def _ensure_nltk_data() -> None:
    """Verify required NLTK tokenizer data is present.

    Raises RuntimeError if missing.
    """
    global _NLTK_INITIALISED
    if _NLTK_INITIALISED:
        return
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            raise RuntimeError(
                f"Required NLTK resource '{resource}' is not installed. "
                f"Run: python -m nltk.downloader {resource}"
            ) from None
    _NLTK_INITIALISED = True


# -----------------------------------------------------------------------
# Main function
# -----------------------------------------------------------------------


def chunk_document(
    metadata_doc: dict[str, Any],
    chunking_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    doc_meta = metadata_doc.get("doc_meta", {})
    pages = metadata_doc.get("pages", [])

    # Step 1: collect all blocks with include_in_chunks=True
    all_blocks: list[dict[str, Any]] = []
    for page in pages:
        for block in page.get("blocks", []):
            if block.get("include_in_chunks", False):
                all_blocks.append(block)

    chunk_settings = _resolve_chunk_settings(chunking_config)
    max_chunk_tokens = chunk_settings["max_chunk_tokens"]
    overlap_tokens = chunk_settings["overlap_tokens"]

    # Step 2: separate tables from text
    table_blocks = [b for b in all_blocks if b.get("content_type") == "table"]
    text_blocks = [b for b in all_blocks if b.get("content_type") != "table"]

    chunks: list[dict[str, Any]] = []
    chunk_index = 0

    # Table blocks → one chunk each
    for block in table_blocks:
        chunk = make_table_chunk(block, doc_meta, chunk_index)
        chunks.append(chunk)
        chunk_index += 1

    # Step 3: group text blocks by section_path
    section_groups = group_blocks_by_section(text_blocks)

    # Step 4: merge short sections
    section_groups = merge_short_sections(section_groups)

    # Steps 5-9: chunk each section group
    overlap_sentences: list[str] = []
    for group in section_groups:
        new_chunks, overlap_sentences = chunk_section_group(
            blocks=group,
            doc_meta=doc_meta,
            chunk_index_start=chunk_index,
            overlap_sentences=overlap_sentences,
            max_chunk_tokens=max_chunk_tokens,
            overlap_tokens=overlap_tokens,
        )
        chunks.extend(new_chunks)
        chunk_index += len(new_chunks)

    # Sort by page then original block order instead of chunk_index
    chunks.sort(key=lambda c: (c["page_start"], c["_source_order"]))

    # Re-assign chunk_index after sort
    for i, chunk in enumerate(chunks):
        chunk["chunk_index"] = i
        del chunk["_source_order"]

    n_text = sum(1 for c in chunks if c["content_type"] == "text")
    n_table = sum(1 for c in chunks if c["content_type"] == "table")
    n_merged = sum(
        1
        for g in section_groups
        if len({tuple(b.get("section_path", [])) for b in g}) > 1
    )

    logger.info(f"Total chunks: {len(chunks)}, text: {n_text}, table: {n_table}")
    logger.info(f"Short sections merged: {n_merged}")
    if chunks:
        logger.debug(f"Example chunk: {chunks[0]['citation']}")

    return {
        **metadata_doc,
        "chunks": chunks,
    }


def _resolve_chunk_settings(config: dict[str, Any] | None) -> dict[str, int]:
    """Resolve runtime chunking settings with backward-compatible defaults."""
    settings = config or {}
    target_chunk_size = int(settings.get("target_chunk_size", MAX_CHUNK_TOKENS))

    if "overlap_tokens" in settings:
        overlap_tokens = int(settings["overlap_tokens"])
    elif "overlap_percentage" in settings:
        overlap_tokens = max(
            int(target_chunk_size * float(settings["overlap_percentage"])),
            0,
        )
    else:
        overlap_tokens = OVERLAP_TOKENS

    return {
        "max_chunk_tokens": target_chunk_size,
        "overlap_tokens": overlap_tokens,
    }


# -----------------------------------------------------------------------
# Token counting + sentence splitting
# -----------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return shared_count_tokens(text)


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using nltk.sent_tokenize."""
    _ensure_nltk_data()
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
        "source_path": doc_meta.get("source_path", ""),
        "_source_order": block.get("block_id", 0),
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


def chunk_section_group(
    blocks: list[dict[str, Any]],
    doc_meta: dict[str, Any],
    chunk_index_start: int,
    overlap_sentences: list[str],
    max_chunk_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Split a section group into sentence-aligned chunks with overlap.

    Returns (chunks, last_overlap_sentences)
    """
    if not blocks:
        return [], []

    sentence_block_pairs: list[tuple[str, dict[str, Any]]] = []
    for block in blocks:
        text = block.get("text", "").strip()
        if not text:
            continue
        for s in split_into_sentences(text):
            sentence_block_pairs.append((s, block))

    if not sentence_block_pairs:
        return [], []

    chunks: list[dict[str, Any]] = []
    chunk_index = chunk_index_start

    current_pairs: list[tuple[str, dict[str, Any]]] = [
        (sentence, blocks[0]) for sentence in overlap_sentences
    ]

    i = 0
    while i < len(sentence_block_pairs):
        sentence, block = sentence_block_pairs[i]
        sentence_tokens = count_tokens(sentence)

        # If a single sentence exceeds the chunk budget, emit any pending
        # content first, then emit the oversized sentence on its own. This
        # avoids getting stuck retrying the same sentence forever when
        # overlap text is already present.
        if sentence_tokens > max_chunk_tokens:
            if current_pairs:
                chunk = _build_text_chunk(
                    sentences=[
                        current_sentence for current_sentence, _ in current_pairs
                    ],
                    contributing_blocks=[
                        current_block for _, current_block in current_pairs
                    ],
                    doc_meta=doc_meta,
                    chunk_index=chunk_index,
                )
                if chunk:
                    chunks.append(chunk)
                    chunk_index += 1
                current_pairs = []
                continue

            chunk = _build_text_chunk(
                sentences=[sentence],
                contributing_blocks=[block],
                doc_meta=doc_meta,
                chunk_index=chunk_index,
            )
            if chunk:
                chunks.append(chunk)
                chunk_index += 1
            i += 1
            continue

        candidate_pairs = [*current_pairs, (sentence, block)]
        candidate = [current_sentence for current_sentence, _ in candidate_pairs]
        candidate_tokens = count_tokens(" ".join(candidate))

        if candidate_tokens > max_chunk_tokens and current_pairs:
            chunk = _build_text_chunk(
                sentences=[current_sentence for current_sentence, _ in current_pairs],
                contributing_blocks=[
                    current_block for _, current_block in current_pairs
                ],
                doc_meta=doc_meta,
                chunk_index=chunk_index,
            )
            if chunk:
                chunks.append(chunk)
                chunk_index += 1

            overlap_sentences = _compute_overlap(
                [current_sentence for current_sentence, _ in current_pairs],
                overlap_tokens=overlap_tokens,
            )
            overlap_count = len(overlap_sentences)
            if overlap_count >= len(current_pairs):
                # If overlap would preserve the whole emitted chunk, the next
                # iteration cannot make progress and can loop forever under
                # tighter chunk budgets. Drop overlap in that case.
                current_pairs = []
            else:
                current_pairs = (
                    current_pairs[-overlap_count:] if overlap_count > 0 else []
                )
        else:
            current_pairs.append((sentence, block))
            i += 1

    # Emit remaining
    if current_pairs:
        chunk = _build_text_chunk(
            sentences=[current_sentence for current_sentence, _ in current_pairs],
            contributing_blocks=[current_block for _, current_block in current_pairs],
            doc_meta=doc_meta,
            chunk_index=chunk_index,
        )
        if chunk:
            chunks.append(chunk)

    # Carry a small overlap across section boundaries so retrieval can
    # find content that spans adjacent sections.
    final_overlap = _compute_overlap(
        [s for s, _ in current_pairs] if not chunks else
        [s for s, _ in sentence_block_pairs[-3:]],
        overlap_tokens=overlap_tokens,
    ) if sentence_block_pairs else []
    return chunks, final_overlap


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
    page_range = (
        str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
    )

    section_path = contributing_blocks[0].get("section_path", ["Unknown"])
    section_title = contributing_blocks[0].get("section_title", "Unknown")

    block_uids = list(
        dict.fromkeys(
            b.get("block_uid", "") for b in contributing_blocks if b.get("block_uid")
        )
    )

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
        "source_path": doc_meta.get("source_path", ""),
        "_source_order": min(b.get("block_id", 0) for b in contributing_blocks),
    }


def _compute_overlap(
    sentences: list[str],
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Take sentences from end of list until overlap token budget is reached."""
    overlap: list[str] = []
    for sentence in reversed(sentences):
        candidate = [sentence, *overlap]
        if count_tokens(" ".join(candidate)) > overlap_tokens:
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
        "doc_type": doc_meta.get("doc_type", ""),
        "specialty": doc_meta.get("specialty", ""),
        "title": doc_meta.get("title", ""),
        "author_org": doc_meta.get("author_org", ""),
        "creation_date": doc_meta.get("creation_date", ""),
        "publish_date": doc_meta.get("publish_date", ""),
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

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

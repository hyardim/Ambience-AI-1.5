from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import Any

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# A4 page height in points (NICE/BSR guidelines are A4)
PAGE_HEIGHT = 842.0
HEADER_THRESHOLD = 0.15
FOOTER_THRESHOLD = 0.85
REPEAT_THRESHOLD = 0.6
Y_BUCKET_SIZE = 10


def clean_document(raw_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Clean extracted PDF text by removing noise and normalizing formatting.

    Args:
        raw_doc: RawDocument dict from extract_pdf.py

    Returns:
        dict: CleanDocument with same structure but cleaned text

    Processing steps:
        1. Unicode normalization (NFKC)
        2. Whitespace normalization
        3. Fix hyphenated line breaks
        4. Normalize bullets and lists
        5. Remove repeated headers/footers
        6. Remove duplicate pages
        7. Remove empty blocks
    """
    pages = raw_doc.get("pages", [])
    num_pages = len(pages)
    total_blocks = sum(len(p["blocks"]) for p in pages)

    logger.info(
        f"Before cleaning: {total_blocks} blocks across {num_pages} pages"
    )

    # Steps 1-4: clean each block's text
    for page in pages:
        for block in page["blocks"]:
            text = block["text"]
            text = _normalize_unicode(text)
            text = _normalize_whitespace(text)
            text = _fix_hyphenated_line_breaks(text)
            text = _normalize_bullets_and_lists(text)
            block["text"] = text

    # Step 5: remove repeated headers/footers
    pages, removed_headers = _remove_repeated_headers_footers(pages, num_pages)

    # Step 6: remove duplicate pages
    pages, removed_pages = _remove_duplicate_pages(pages)

    # Step 7: remove empty blocks
    for page in pages:
        page["blocks"] = [b for b in page["blocks"] if b["text"].strip()]

    final_blocks = sum(len(p["blocks"]) for p in pages)
    final_pages = len(pages)

    logger.info(f"Removed {removed_headers} header/footer blocks")
    logger.info(f"Removed {removed_pages} duplicate pages")
    logger.info(
        f"After cleaning: {final_blocks} blocks across {final_pages} pages"
    )

    return {
        **raw_doc,
        "pages": pages,
    }


def _normalize_unicode(text: str) -> str:
    """Apply NFKC Unicode normalization.

    Converts ligatures and visually similar characters to canonical form.
    Example: 'ﬁ' → 'fi'

    Args:
        text: Raw block text

    Returns:
        NFKC normalized text
    """
    return unicodedata.normalize("NFKC", text)


def _normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    - Normalizes line endings to \\n
    - Collapses multiple spaces to single space
    - Collapses 3+ newlines to max 2
    - Trims leading/trailing whitespace

    Args:
        text: Block text

    Returns:
        Whitespace-normalized text
    """
    text = text.replace("\r\n", "\n")
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fix_hyphenated_line_breaks(text: str) -> str:
    """Merge words broken across lines by hyphens.

    Only merges when:
    - Hyphen is at end of line
    - Next line starts with lowercase letter
    - Both sides are alphabetic

    Preserves legitimate hyphens like 'COVID-19', 'anti-inflammatory'.

    Args:
        text: Block text

    Returns:
        Text with hyphenated line breaks merged
    """
    return re.sub(r"([a-zA-Z]+)-\n([a-z][a-zA-Z]*)", r"\1\2", text)


def _normalize_bullets_and_lists(text: str) -> str:
    """Normalize bullet points and list markers.

    Bullet conversions: •, ◦, ▪, ▸, ➢, ✓, – → '- '
    Numbered list: '1)' → '1.', '(1)' → '1.'
    Lettered list: 'a)' → 'a.', '(a)' → 'a.'

    Args:
        text: Block text

    Returns:
        Text with normalized list markers
    """
    # Normalize bullet characters to '- '
    text = re.sub(r"^[•◦▪▸➢✓–]\s*", "- ", text, flags=re.MULTILINE)

    # Normalize numbered lists
    text = re.sub(r"^(\d+)\)\s*", r"\1. ", text, flags=re.MULTILINE)
    text = re.sub(r"^\((\d+)\)\s*", r"\1. ", text, flags=re.MULTILINE)

    # Normalize lettered lists
    text = re.sub(r"^([a-z])\)\s*", r"\1. ", text, flags=re.MULTILINE)
    text = re.sub(r"^\(([a-z])\)\s*", r"\1. ", text, flags=re.MULTILINE)

    return text


def _remove_repeated_headers_footers(
    pages: list[dict[str, Any]],
    num_pages: int,
) -> tuple[list[dict[str, Any]], int]:
    """Remove blocks that appear repeatedly in header/footer positions.

    Uses position + frequency heuristic:
    - Top blocks: bbox[1] < page_height * 0.15
    - Bottom blocks: bbox[3] > page_height * 0.85
    - Groups by (normalized_text, y_bucket)
    - Removes if appears on >= 60% of pages

    Args:
        pages: List of page dicts
        num_pages: Total number of pages for frequency calculation

    Returns:
        Tuple of (cleaned pages, number of blocks removed)
    """
    if num_pages == 0:
        return pages, 0

    # Count (normalized_text, y_bucket) pairs across pages
    pattern_page_counts: dict[tuple[str, int], set[int]] = defaultdict(set)

    for page in pages:
        page_num = page["page_number"]
        for block in page["blocks"]:
            bbox = block["bbox"]
            y0, y3 = bbox[1], bbox[3]

            is_header = y0 < PAGE_HEIGHT * HEADER_THRESHOLD
            is_footer = y3 > PAGE_HEIGHT * FOOTER_THRESHOLD

            if not (is_header or is_footer):
                continue

            normalized = block["text"].lower().strip()
            y_bucket = round(y0 / Y_BUCKET_SIZE) * Y_BUCKET_SIZE
            pattern_page_counts[(normalized, y_bucket)].add(page_num)

    # Identify patterns that appear on >= 60% of pages
    patterns_to_remove: set[tuple[str, int]] = set()
    for pattern, page_set in pattern_page_counts.items():
        if len(page_set) / num_pages >= REPEAT_THRESHOLD:
            patterns_to_remove.add(pattern)

    # Remove matching blocks from all pages
    removed_count = 0
    for page in pages:
        original_count = len(page["blocks"])
        page["blocks"] = [
            b
            for b in page["blocks"]
            if not _is_header_footer_block(b, patterns_to_remove)
        ]
        removed_count += original_count - len(page["blocks"])

    return pages, removed_count


def _is_header_footer_block(
    block: dict[str, Any],
    patterns_to_remove: set[tuple[str, int]],
) -> bool:
    """Check if a block matches a repeated header/footer pattern.

    Args:
        block: Block dict with text and bbox
        patterns_to_remove: Set of (normalized_text, y_bucket) patterns

    Returns:
        True if block should be removed
    """
    normalized = block["text"].lower().strip()
    y0 = block["bbox"][1]
    y_bucket = round(y0 / Y_BUCKET_SIZE) * Y_BUCKET_SIZE
    return (normalized, y_bucket) in patterns_to_remove

def _remove_duplicate_pages(
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Remove duplicate pages using MD5 hash of concatenated block text.

    Keeps first occurrence, removes subsequent duplicates.

    Args:
        pages: List of page dicts

    Returns:
        Tuple of (deduplicated pages, number of pages removed)
    """
    seen_hashes: set[str] = set()
    unique_pages: list[dict[str, Any]] = []

    for page in pages:
        page_text = "\n".join(block["text"] for block in page["blocks"])
        page_hash = hashlib.md5(page_text.encode("utf-8")).hexdigest()

        if page_hash not in seen_hashes:
            seen_hashes.add(page_hash)
            unique_pages.append(page)

    removed = len(pages) - len(unique_pages)
    return unique_pages, removed

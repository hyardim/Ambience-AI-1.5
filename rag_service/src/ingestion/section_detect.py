from __future__ import annotations

import re
from statistics import median
from typing import Any

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

EXCLUDED_SECTIONS = {
    "authors",
    "author",
    "contributors",
    "affiliations",
    "references",
    "bibliography",
    "citations",
    "works cited",
    "acknowledgments",
    "acknowledgements",
    "disclosures",
    "conflicts of interest",
    "conflict of interest",
    "appendix",
    "appendices",
}

BULLET_PATTERN = re.compile(r"^[-•\d]")
NUMBERED_HEADING_PATTERN = re.compile(r"^(\d+(\.\d+)*\.?)\s+([A-Z][a-zA-Z\s]{2,})$")

def add_section_metadata(clean_doc: dict[str, Any]) -> dict[str, Any]:
    """
    Detect headings and assign section metadata to all blocks.

    Args:
        clean_doc: CleanDocument dict from clean_text.py

    Returns:
        dict: SectionedDocument with added fields per block:
            - is_heading: bool
            - heading_level: int | None
            - section_path: list[str]
            - section_title: str
            - include_in_chunks: bool

    Processing steps:
        1. Detect heading candidates using priority-ordered rules
        2. Assign heading levels
        3. Build section paths using stack algorithm
        4. Mark excluded sections (authors, references)
    """
    pass

def _detect_heading(
    block: dict[str, Any],
    text: str,
    page_median: float,
) -> tuple[bool, int, str, str | None]:
    """Apply heading detection rules in priority order.

    Args:
        block: Block dict with font metadata
        text: Stripped block text
        page_median: Median font size for the page

    Returns:
        (is_heading, level, clean_text, heading_type)
    """
    pass

def _compute_page_median_font_size(blocks: list[dict[str, Any]]) -> float:
    """Compute median font size for a page from blocks with font_size > 0.

    Args:
        blocks: List of block dicts

    Returns:
        Median font size, or 0.0 if no valid font sizes
    """
    sizes = [b["font_size"] for b in blocks if b.get("font_size", 0) > 0]
    return float(median(sizes)) if sizes else 0.0

def is_numbered_heading(text: str) -> tuple[bool, int, str]:
    """Check if text matches numbered heading pattern.

    Pattern: starts with numeric prefix (1, 2.1, 3.2.1) followed by
    capitalized text of at least 3 characters.

    Args:
        text: Block text to check

    Returns:
        (is_match, level, clean_text) where level is depth and
        clean_text has the numeric prefix stripped
    """
    match = NUMBERED_HEADING_PATTERN.match(text.strip())
    if not match:
        return False, 0, text

    number_part = match.group(1)  # e.g. "2.1" or "2.1."
    clean_text = match.group(3)   # e.g. "Monitoring"

    # Level = number of dots + 1 (strip trailing dot first)
    stripped = number_part.rstrip(".")
    level = stripped.count(".") + 1

    return True, level, clean_text

def is_allcaps_heading(text: str) -> bool:
    """Check if text is an all-caps heading.

    Requirements:
    - 100% uppercase
    - Length <= 80 characters
    - Fewer than 10 words
    - Does not start with bullet/list marker

    Args:
        text: Block text to check

    Returns:
        True if text qualifies as all-caps heading
    """
    stripped = text.strip()

    if not stripped:
        return False

    if BULLET_PATTERN.match(stripped):
        return False

    if len(stripped) > 80:
        return False

    words = stripped.split()
    if len(words) >= 10:
        return False

    # Must be 100% uppercase — filter out non-alpha chars before checking
    alpha_chars = [c for c in stripped if c.isalpha()]
    if not alpha_chars:
        return False

    return all(c.isupper() for c in alpha_chars)

def is_bold_heading(block: dict[str, Any]) -> bool:
    """Check if block qualifies as a bold heading.

    Requirements:
    - is_bold = True
    - Length <= 100 characters
    - Fewer than 15 words
    - Not all-caps (caught by Rule B)
    - Does not start with bullet/list marker

    Args:
        block: Block dict with text and is_bold fields

    Returns:
        True if block qualifies as bold heading
    """
    if not block.get("is_bold", False):
        return False

    text = block.get("text", "").strip()

    if not text:
        return False

    if BULLET_PATTERN.match(text):
        return False

    if len(text) > 100:
        return False

    words = text.split()
    if len(words) >= 15:
        return False

    # Skip if all-caps — already caught by Rule B
    alpha_chars = [c for c in text if c.isalpha()]
    if alpha_chars and all(c.isupper() for c in alpha_chars):
        return False

    return True

def is_excluded_section(section_title: str) -> bool:
    """Check if section should be excluded from chunks.

    Matches against known non-content section titles like
    References, Authors, Acknowledgments etc.

    Args:
        section_title: Section title to check

    Returns:
        True if section should be excluded from chunking
    """
    title_lower = section_title.lower().strip()
    return any(excluded in title_lower for excluded in EXCLUDED_SECTIONS)

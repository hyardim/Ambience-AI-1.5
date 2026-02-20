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

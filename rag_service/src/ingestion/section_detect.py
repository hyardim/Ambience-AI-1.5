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

from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.citation import (
    Citation,
    CitationError,
    CitedResult,
    assemble_citations,
    format_citation,
    format_section_path,
)
from src.retrieval.rerank import RankedResult
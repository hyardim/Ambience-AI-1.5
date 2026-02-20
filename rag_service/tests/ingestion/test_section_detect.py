from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.section_detect import (
    _compute_page_median_font_size,
    _detect_heading,
    add_section_metadata,
    is_allcaps_heading,
    is_bold_heading,
    is_excluded_section,
    is_fontsize_heading,
    is_numbered_heading,
)

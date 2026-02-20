from __future__ import annotations

from typing import Any

from src.ingestion.clean import (
    _fix_hyphenated_line_breaks,
    _is_header_footer_block,
    _normalize_bullets_and_lists,
    _normalize_unicode,
    _normalize_whitespace,
    _remove_duplicate_pages,
    _remove_repeated_headers_footers,
    clean_document,
)
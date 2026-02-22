from __future__ import annotations

from typing import Any

import pytest

from src.ingestion.chunk import (
    MAX_CHUNK_TOKENS,
    MAX_MERGE_SECTIONS,
    MIN_CHUNK_TOKENS,
    OVERLAP_TOKENS,
    SHORT_SECTION_TOKENS,
    build_citation,
    chunk_document,
    chunk_section_group,
    clean_chunk_text,
    count_tokens,
    generate_chunk_id,
    group_blocks_by_section,
    make_table_chunk,
    merge_short_sections,
    split_into_sentences,
)
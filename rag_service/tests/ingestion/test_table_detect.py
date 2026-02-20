from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.table_detect import (
    _is_pipe_table_block,
    _normalize_cell,
    bboxes_overlap,
    cells_to_markdown,
    detect_and_convert_tables,
    detect_header_row,
    detect_tables_with_pymupdf,
    find_overlapping_blocks,
    find_table_caption,
)

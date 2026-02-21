from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.metadata import (
    MetadataValidationError,
    attach_metadata,
    extract_pdf_metadata,
    extract_title,
    generate_block_uid,
    generate_doc_id,
    generate_doc_version,
    infer_from_path,
    parse_pdf_date,
    validate_metadata,
    validate_source_info,
)

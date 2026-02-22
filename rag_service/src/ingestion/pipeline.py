from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from ..utils.logger import setup_logger
from .chunk import chunk_document
from .clean import clean_document
from .embed import embed_chunks
from .extract import extract_raw_document
from .metadata import attach_metadata
from .section_detect import add_section_metadata
from .store import store_chunks
from .table_detect import detect_and_convert_tables

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_VERSION = "main"
DEFAULT_EMBEDDING_DIMENSIONS = 384
DEFAULT_CHUNK_SIZE = 450
DEFAULT_OVERLAP = 0.15
DEFAULT_LOG_LEVEL = "INFO"

STAGE_EXTRACT = "EXTRACT"
STAGE_CLEAN = "CLEAN"
STAGE_SECTION = "SECTION"
STAGE_TABLE = "TABLE"
STAGE_METADATA = "METADATA"
STAGE_CHUNK = "CHUNK"
STAGE_EMBED = "EMBED"
STAGE_STORE = "STORE"
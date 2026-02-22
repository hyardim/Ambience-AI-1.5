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

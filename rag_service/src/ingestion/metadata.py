from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_SPECIALTIES = {"neurology", "rheumatology"}
VALID_SOURCE_NAMES = {"NICE", "BSR", "Others"}
VALID_DOC_TYPES = {"guideline", "protocol", "policy", "standard"}

class MetadataValidationError(Exception):
    """Raised when metadata validation fails."""
    pass
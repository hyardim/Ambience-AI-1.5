from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from ..utils.logger import setup_logger

logger = setup_logger(__name__)


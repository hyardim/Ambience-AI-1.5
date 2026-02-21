from __future__ import annotations

import hashlib
from typing import Any

import nltk
import tiktoken

from ..utils.logger import setup_logger

nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)
from nltk.tokenize import sent_tokenize  # noqa: E402

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

MIN_CHUNK_TOKENS = 300
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 80
SHORT_SECTION_TOKENS = 150
MAX_MERGE_SECTIONS = 2

_ENCODER = tiktoken.get_encoding("cl100k_base")


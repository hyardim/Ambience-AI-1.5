from __future__ import annotations

import time
from typing import Any

from sentence_transformers import SentenceTransformer

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MODEL_VERSION = "main"
EMBEDDING_DIMENSIONS = 384
EMBEDDING_BATCH_SIZE = 32
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0  # seconds, doubled each retry

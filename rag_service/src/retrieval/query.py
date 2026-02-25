from __future__ import annotations

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAX_QUERY_TOKENS = 512

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..utils.logger import setup_logger
from .citation import CitedResult, assemble_citations
from .filters import FilterConfig, apply_filters
from .fusion import reciprocal_rank_fusion
from .keyword_search import keyword_search
from .query import RetrievalError, process_query
from .rerank import deduplicate, rerank
from .vector_search import vector_search

logger = setup_logger(__name__)

DEBUG_ARTIFACT_DIR = Path("data/debug/retrieval")

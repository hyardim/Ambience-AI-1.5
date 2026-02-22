from __future__ import annotations

import time
from typing import Any

from sentence_transformers import SentenceTransformer

from ..utils.logger import setup_logger

logger = setup_logger(__name__)
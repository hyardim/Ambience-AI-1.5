from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import src.ingestion.embed as embed_module
from src.ingestion.embed import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_MODEL_VERSION,
    MAX_RETRIES,
    _embed_batch,
    _embed_single,
    _make_failure_fields,
    _make_success_fields,
    embed_chunks,
)
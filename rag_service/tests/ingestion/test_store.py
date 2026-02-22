from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from src.ingestion.store import (
    _build_metadata,
    _metadata_json,
    _upsert_chunk,
    store_chunks,
)
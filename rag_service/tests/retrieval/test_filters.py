from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.retrieval.filters import FilterConfig, apply_filters
from src.retrieval.fusion import FusedResult


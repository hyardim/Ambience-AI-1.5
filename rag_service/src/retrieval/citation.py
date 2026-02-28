from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..utils.logger import setup_logger
from .rerank import RankedResult

logger = setup_logger(__name__)

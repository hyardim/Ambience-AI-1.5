from __future__ import annotations

import json
from typing import Any

from pgvector.psycopg2 import register_vector

from ...src.utils.db import db
from ..utils.logger import setup_logger

logger = setup_logger(__name__)
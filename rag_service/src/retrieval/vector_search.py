from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

from .query import RetrievalError
from ..utils.logger import setup_logger

logger = setup_logger(__name__)
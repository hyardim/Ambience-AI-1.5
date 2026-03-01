from __future__ import annotations

import os
import sys

import click
from dotenv import load_dotenv

from ..utils.logger import setup_logger
from .citation import format_citation
from .query import RetrievalError
from .retrieve import retrieve

logger = setup_logger(__name__)

_SEPARATOR = "─" * 49

from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path

import click

from ..utils.logger import setup_logger
from .pipeline import run_ingestion

logger = setup_logger(__name__)

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.ingestion.cli import _configure_log_level, _resolve_db_url, cli

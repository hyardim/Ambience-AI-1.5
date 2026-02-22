from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.ingestion.pipeline import (
    PipelineError,
    _strip_embeddings,
    discover_pdfs,
    load_ingestion_config,
    load_sources,
    run_ingestion,
    run_pipeline,
)

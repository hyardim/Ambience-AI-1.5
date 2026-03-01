from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.retrieval.citation import Citation, CitedResult
from src.retrieval.cli import main
from src.retrieval.query import RetrievalError

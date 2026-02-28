from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from src.retrieval.query import RetrievalError
from src.retrieval.keyword_search import KeywordSearchResult, keyword_search

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

QUERY = "methotrexate dosage"


def make_row(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    rank: float = 0.72,
    specialty: str = "rheumatology",
    source_name: str = "NICE",
    doc_type: str = "guideline",
    source_url: str = "https://nice.org.uk",
    content_type: str = "text",
    section_title: str = "Treatment",
    title: str = "RA Guidelines",
    page_start: int = 1,
    page_end: int = 2,
    section_path: list[str] | None = None,
) -> tuple:
    return (
        chunk_id,
        doc_id,
        text,
        rank,
        specialty,
        source_name,
        doc_type,
        source_url,
        content_type,
        section_title,
        title,
        page_start,
        page_end,
        section_path or ["Treatment"],
    )

def make_mock_conn(
    rows: list[tuple],
    tsquery_result: str = "methotrexate & dosage",
    tsvector_exists: bool = True,
) -> MagicMock:
    """
    Return a mock psycopg2 connection.

    Handles three cursor.execute calls in order:
      1. _check_tsvector_column — returns column row or None
      2. _is_stopword_only_query — returns tsquery string
      3. _run_query — returns search result rows
    """
    cursors = []

    # cursor 1: tsvector column check
    col_cursor = MagicMock()
    col_cursor.fetchone.return_value = ("text_search_vector",) if tsvector_exists else None
    col_cursor.__enter__ = lambda s: s
    col_cursor.__exit__ = MagicMock(return_value=False)
    cursors.append(col_cursor)

    # cursor 2: stopword check
    stop_cursor = MagicMock()
    stop_cursor.fetchone.return_value = (tsquery_result,)
    stop_cursor.__enter__ = lambda s: s
    stop_cursor.__exit__ = MagicMock(return_value=False)
    cursors.append(stop_cursor)

    # cursor 3: main query
    query_cursor = MagicMock()
    query_cursor.fetchall.return_value = rows
    query_cursor.__enter__ = lambda s: s
    query_cursor.__exit__ = MagicMock(return_value=False)
    cursors.append(query_cursor)

    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = cursors
    return mock_conn
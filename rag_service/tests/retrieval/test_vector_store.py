from __future__ import annotations

from unittest.mock import MagicMock, patch

import src.retrieval.vector_store as vector_store


def make_conn(row: tuple | None):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.return_value = row
    cur.fetchall.return_value = []
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


def test_get_source_path_for_doc_returns_value() -> None:
    conn, cur = make_conn(("/data/raw/neurology/test.pdf",))
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        result = vector_store.get_source_path_for_doc("doc123")
    cur.execute.assert_called_once()
    conn.close.assert_called_once()
    assert result == "/data/raw/neurology/test.pdf"


def test_get_source_path_for_doc_returns_none_when_null() -> None:
    conn, cur = make_conn((None,))
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        result = vector_store.get_source_path_for_doc("doc123")
    cur.execute.assert_called_once()
    conn.close.assert_called_once()
    assert result is None


def test_get_source_path_for_doc_handles_absent_row() -> None:
    conn, cur = make_conn(None)
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        result = vector_store.get_source_path_for_doc("doc123")
    cur.execute.assert_called_once()
    conn.close.assert_called_once()
    assert result is None


def test_search_similar_chunks_applies_specialty_filter_when_provided() -> None:
    conn, cur = make_conn(None)
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        vector_store.search_similar_chunks(
            [0.1, 0.2],
            limit=3,
            specialty="neurology",
        )

    cur.execute.assert_called_once()
    _, params = cur.execute.call_args.args
    assert params == ([0.1, 0.2], "neurology", "neurology", [0.1, 0.2], 3)
    conn.close.assert_called_once()


def test_search_similar_chunks_skips_specialty_filter_when_not_provided() -> None:
    conn, cur = make_conn(None)
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        vector_store.search_similar_chunks([0.1, 0.2], limit=3)

    cur.execute.assert_called_once()
    _, params = cur.execute.call_args.args
    assert params == ([0.1, 0.2], None, None, [0.1, 0.2], 3)
    conn.close.assert_called_once()

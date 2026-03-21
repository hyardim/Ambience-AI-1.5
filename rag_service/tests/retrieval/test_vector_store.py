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


def test_get_conn_enables_autocommit() -> None:
    conn = MagicMock()
    with (
        patch(
            "src.retrieval.vector_store.db_config",
            new=MagicMock(database_url="postgresql://db.example/test"),
        ),
        patch(
            "src.retrieval.vector_store.psycopg2.connect", return_value=conn
        ) as mock_connect,
    ):
        result = vector_store.get_conn()

    mock_connect.assert_called_once_with("postgresql://db.example/test")
    assert result is conn
    assert conn.autocommit is True


def test_init_db_executes_schema_sql() -> None:
    conn, cur = make_conn(None)
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        vector_store.init_db(384)

    assert cur.execute.call_count == 3
    schema_sql = cur.execute.call_args_list[2].args[0]
    assert "rag_chunks_embedding_idx" in schema_sql
    assert "idx_rag_chunks_embedding_hnsw" in schema_sql
    conn.close.assert_called_once()

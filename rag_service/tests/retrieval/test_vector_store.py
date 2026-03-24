from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import src.retrieval.vector_store as vector_store


def make_conn(rows: list[tuple]):
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchall.return_value = rows
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


@contextmanager
def yield_conn(conn):
    yield conn


def test_get_source_path_for_doc_returns_value(tmp_path: Path) -> None:
    source = tmp_path / "neurology" / "test.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("pdf")
    conn, cur = make_conn([(str(source), None)])
    with patch.object(vector_store.db, "raw_connection", return_value=yield_conn(conn)):
        result = vector_store.get_source_path_for_doc("doc123")
    cur.execute.assert_called_once()
    assert result == str(source)


def test_get_source_path_for_doc_resolves_relative_path() -> None:
    relative = Path("data/raw/_tmp/vector-store-relative-test.pdf")
    resolved = vector_store.path_config.root / relative
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text("pdf")
    conn, cur = make_conn([(str(relative), None)])
    try:
        with patch.object(
            vector_store.db, "raw_connection", return_value=yield_conn(conn)
        ):
            result = vector_store.get_source_path_for_doc("doc123")
        cur.execute.assert_called_once()
        assert result == str(resolved.resolve())
    finally:
        resolved.unlink(missing_ok=True)


def test_get_source_path_for_doc_returns_none_when_no_rows() -> None:
    conn, cur = make_conn([])
    with patch.object(vector_store.db, "raw_connection", return_value=yield_conn(conn)):
        result = vector_store.get_source_path_for_doc("doc123")
    cur.execute.assert_called_once()
    assert result is None


def test_get_source_path_for_doc_falls_back_to_latest_when_missing() -> None:
    conn, cur = make_conn(
        [
            ("/missing/newer.pdf", None),
            ("/missing/older.pdf", None),
        ]
    )
    with patch.object(vector_store.db, "raw_connection", return_value=yield_conn(conn)):
        result = vector_store.get_source_path_for_doc("doc123")
    cur.execute.assert_called_once()
    assert result == "/missing/newer.pdf"


def test_get_source_path_for_doc_remaps_host_absolute_data_path() -> None:
    local = vector_store.path_config.data_raw / "_tmp" / "vector-store-remap-test.pdf"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("pdf")
    host_style = (
        "/Users/example/project/rag_service/data/raw/"
        "_tmp/vector-store-remap-test.pdf"
    )
    conn, cur = make_conn([(host_style, None)])
    try:
        with patch.object(
            vector_store.db, "raw_connection", return_value=yield_conn(conn)
        ):
            result = vector_store.get_source_path_for_doc("doc123")
        cur.execute.assert_called_once()
        assert result == str(local.resolve())
    finally:
        local.unlink(missing_ok=True)


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

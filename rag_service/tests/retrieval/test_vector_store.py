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
        "/Users/example/project/rag_service/data/raw/_tmp/vector-store-remap-test.pdf"
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


def test_remap_source_path_returns_none_when_no_data_raw_marker() -> None:
    result = vector_store._remap_source_path_to_data_root(
        "/some/random/path/without/marker.pdf"
    )
    assert result is None


def test_remap_source_path_returns_none_for_empty_tail() -> None:
    result = vector_store._remap_source_path_to_data_root("/some/project/data/raw/")
    assert result is None


def test_get_source_path_for_doc_skips_empty_source_path(
    tmp_path,
) -> None:
    """Cover line 112: continue when source_path is empty."""
    real_file = tmp_path / "real.pdf"
    real_file.write_text("pdf")
    conn, _cur = make_conn(
        [
            ("", None),
            (str(real_file), None),
        ]
    )
    with patch.object(vector_store.db, "raw_connection", return_value=yield_conn(conn)):
        result = vector_store.get_source_path_for_doc("doc123")
    # Empty source_path is skipped; second row resolves to the real file
    assert result == str(real_file)


def test_get_source_path_for_doc_skips_duplicate_candidate_paths() -> None:
    """Cover line 126: when remap produces path already in candidates."""
    data_raw = vector_store.path_config.data_raw
    file_path = data_raw / "_tmp" / "vector-store-dedup-test.pdf"
    # Use the resolved absolute path. Since it's absolute:
    #   - original = Path(resolved_path) -> added to candidates
    #   - is_absolute() is True -> no root-join candidate
    #   - remap finds /data/raw/ in the path -> produces data_raw/_tmp/file
    #     which resolves to the same path -> duplicate triggers line 126.
    #
    # Keep the file missing so the function doesn't return early on the first
    # candidate; it must evaluate the duplicate candidate and then fall back to
    # the stored source path.
    source_str = str(file_path.resolve())
    conn, _cur = make_conn([(source_str, None)])
    file_path.unlink(missing_ok=True)

    with (
        patch.object(vector_store.db, "raw_connection", return_value=yield_conn(conn)),
        patch(
            "src.retrieval.vector_store._remap_source_path_to_data_root",
            return_value=Path(source_str),
        ),
    ):
        result = vector_store.get_source_path_for_doc("doc123")

    assert result == source_str

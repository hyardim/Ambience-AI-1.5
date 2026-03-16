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


def test_delete_chunks_for_doc_executes_delete() -> None:
    conn, cur = make_conn(None)
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        vector_store.delete_chunks_for_doc("doc-1")

    cur.execute.assert_called_once_with(
        "DELETE FROM rag_chunks WHERE doc_id = %s;",
        ("doc-1",),
    )
    conn.close.assert_called_once()


def test_insert_chunks_returns_early_for_empty_input() -> None:
    with patch("src.retrieval.vector_store.get_conn") as mock_get_conn:
        vector_store.insert_chunks([])

    mock_get_conn.assert_not_called()


def test_insert_chunks_uses_execute_values() -> None:
    conn, cur = make_conn(None)
    chunks = [
        {
            "doc_id": "doc-1",
            "doc_version": "v1",
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "text": "hello",
            "embedding": [0.1, 0.2],
            "metadata": {"section": "Intro"},
        }
    ]

    with (
        patch("src.retrieval.vector_store.get_conn", return_value=conn),
        patch(
            "src.retrieval.vector_store.psycopg2.extras.execute_values"
        ) as mock_execute,
    ):
        vector_store.insert_chunks(chunks)

    mock_execute.assert_called_once()
    conn.close.assert_called_once()


def test_search_similar_chunks_maps_result_fields() -> None:
    conn, cur = make_conn(None)
    cur.fetchall.return_value = [
        (
            1,
            "doc-1",
            "v1",
            "chunk-1",
            0,
            "text/plain",
            "hello",
            {"page_start": 2, "page_end": 3, "section_path": ["A", "B"]},
            0.88,
        )
    ]
    with patch("src.retrieval.vector_store.get_conn", return_value=conn):
        result = vector_store.search_similar_chunks([0.1], limit=1)

    assert result == [
        {
            "id": 1,
            "doc_id": "doc-1",
            "doc_version": "v1",
            "chunk_id": "chunk-1",
            "chunk_index": 0,
            "content_type": "text/plain",
            "text": "hello",
            "metadata": {"page_start": 2, "page_end": 3, "section_path": ["A", "B"]},
            "score": 0.88,
            "page_start": 2,
            "page_end": 3,
            "section_path": "A > B",
        }
    ]


def test_normalize_section_path_handles_none_and_scalar() -> None:
    assert vector_store._normalize_section_path(None) is None
    assert vector_store._normalize_section_path("Section") == "Section"

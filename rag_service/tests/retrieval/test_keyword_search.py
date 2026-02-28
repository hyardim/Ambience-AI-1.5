from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.keyword_search import KeywordSearchResult, keyword_search
from src.retrieval.query import RetrievalError

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
    col_cursor.fetchone.return_value = (
        ("text_search_vector",) if tsvector_exists else None
    )
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


# -----------------------------------------------------------------------
# Auto-mock register_default_jsonb for all tests
# -----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_jsonb():
    """Mock register_default_jsonb — requires a real connection otherwise."""
    with patch("src.retrieval.keyword_search.psycopg2.extras.register_default_jsonb"):
        yield


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestKeywordSearch:
    def test_returns_list_of_keyword_search_results(self):
        mock_conn = make_mock_conn([make_row()])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert isinstance(results, list)
        assert all(isinstance(r, KeywordSearchResult) for r in results)

    def test_result_is_pydantic_model(self):
        mock_conn = make_mock_conn([make_row()])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert hasattr(results[0], "model_dump")

    def test_results_ordered_by_rank_descending(self):
        rows = [make_row(rank=0.9), make_row(rank=0.6), make_row(rank=0.3)]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        ranks = [r.rank for r in results]
        assert ranks == sorted(ranks, reverse=True)

    def test_top_k_passed_as_limit_to_sql(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run:
                keyword_search(QUERY, db_url="postgresql://fake", top_k=5)
        args = mock_run.call_args[0]
        assert args[2] == 5

    def test_specialty_filter_passed_to_run_query(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run:
                keyword_search(
                    QUERY, db_url="postgresql://fake", specialty="rheumatology"
                )
        args = mock_run.call_args[0]
        assert "rheumatology" in args

    def test_source_name_filter_passed_to_run_query(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run:
                keyword_search(QUERY, db_url="postgresql://fake", source_name="NICE")
        args = mock_run.call_args[0]
        assert "NICE" in args

    def test_doc_type_filter_passed_to_run_query(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run:
                keyword_search(QUERY, db_url="postgresql://fake", doc_type="guideline")
        args = mock_run.call_args[0]
        assert "guideline" in args

    def test_multiple_filters_combined(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run:
                keyword_search(
                    QUERY,
                    db_url="postgresql://fake",
                    specialty="rheumatology",
                    source_name="NICE",
                    doc_type="guideline",
                )
        args = mock_run.call_args[0]
        assert "rheumatology" in args
        assert "NICE" in args
        assert "guideline" in args

    def test_no_filters_passes_none_values(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run:
                keyword_search(QUERY, db_url="postgresql://fake")
        args = mock_run.call_args[0]
        assert args[3] is None  # specialty
        assert args[4] is None  # source_name
        assert args[5] is None  # doc_type

    def test_empty_result_returns_empty_list(self):
        mock_conn = make_mock_conn([])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert results == []

    def test_stopword_only_query_returns_empty_list(self):
        mock_conn = make_mock_conn([], tsquery_result="")
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search("the a is", db_url="postgresql://fake")
        assert results == []

    def test_empty_query_raises_retrieval_error(self):
        with pytest.raises(RetrievalError) as exc_info:
            keyword_search("", db_url="postgresql://fake")
        assert exc_info.value.stage == "KEYWORD_SEARCH"

    def test_whitespace_only_query_raises_retrieval_error(self):
        with pytest.raises(RetrievalError) as exc_info:
            keyword_search("   ", db_url="postgresql://fake")
        assert exc_info.value.stage == "KEYWORD_SEARCH"

    def test_zero_top_k_raises_retrieval_error(self):
        with pytest.raises(RetrievalError) as exc_info:
            keyword_search(QUERY, db_url="postgresql://fake", top_k=0)
        assert exc_info.value.stage == "KEYWORD_SEARCH"
        assert "top_k" in exc_info.value.message

    def test_negative_top_k_raises_retrieval_error(self):
        with pytest.raises(RetrievalError) as exc_info:
            keyword_search(QUERY, db_url="postgresql://fake", top_k=-1)
        assert exc_info.value.stage == "KEYWORD_SEARCH"
        assert "top_k" in exc_info.value.message

    def test_db_connection_failure_raises_retrieval_error(self):
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect",
            side_effect=Exception("connection refused"),
        ):
            with pytest.raises(RetrievalError) as exc_info:
                keyword_search(QUERY, db_url="postgresql://fake")
        assert exc_info.value.stage == "KEYWORD_SEARCH"

    def test_missing_tsvector_column_raises_retrieval_error(self):
        mock_conn = make_mock_conn([], tsvector_exists=False)
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            with pytest.raises(RetrievalError) as exc_info:
                keyword_search(QUERY, db_url="postgresql://fake")
        assert exc_info.value.stage == "KEYWORD_SEARCH"
        assert "migration" in exc_info.value.message

    def test_retrieval_error_from_run_query_propagates_unchanged(self):
        mock_conn = make_mock_conn([])
        original_error = RetrievalError(
            stage="KEYWORD_SEARCH",
            query=QUERY,
            message="something specific failed",
        )
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch(
                "src.retrieval.keyword_search._run_query",
                side_effect=original_error,
            ):
                with pytest.raises(RetrievalError) as exc_info:
                    keyword_search(QUERY, db_url="postgresql://fake")
        assert exc_info.value is original_error
        assert exc_info.value.message == "something specific failed"

    def test_connection_closed_after_query(self):
        mock_conn = make_mock_conn([])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            keyword_search(QUERY, db_url="postgresql://fake")
        mock_conn.close.assert_called_once()

    def test_connection_closed_on_failure(self):
        mock_conn = make_mock_conn([])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch(
                "src.retrieval.keyword_search._run_query",
                side_effect=Exception("query failed"),
            ):
                with pytest.raises(RetrievalError):
                    keyword_search(QUERY, db_url="postgresql://fake")
        mock_conn.close.assert_called_once()

    def test_metadata_fields_populated(self):
        rows = [
            make_row(specialty="rheumatology", source_name="NICE", title="RA Guide")
        ]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert results[0].metadata["specialty"] == "rheumatology"
        assert results[0].metadata["source_name"] == "NICE"
        assert results[0].metadata["title"] == "RA Guide"

    def test_null_page_values_default_to_zero(self):
        row = make_row()
        row = row[:11] + (None, None) + row[13:]
        mock_conn = make_mock_conn([row])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert results[0].metadata["page_start"] == 0
        assert results[0].metadata["page_end"] == 0

    def test_section_path_is_list_not_string(self):
        rows = [make_row(section_path=["Treatment", "First-line therapy"])]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert isinstance(results[0].metadata["section_path"], list)
        assert results[0].metadata["section_path"] == [
            "Treatment",
            "First-line therapy",
        ]

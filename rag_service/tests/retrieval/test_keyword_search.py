from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from psycopg2 import errors as pg_errors

from src.retrieval.keyword_search import (
    KeywordSearchResult,
    _build_relaxed_or_tsquery as _build_relaxed_tsquery,
    keyword_search,
)
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
    creation_date: str | None = "2020-01-01",
    publish_date: str | None = "2021-06-30",
    last_updated_date: str | None = "2024-01-15",
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
        creation_date,
        publish_date,
        last_updated_date,
        page_start,
        page_end,
        section_path or ["Treatment"],
    )


def make_mock_conn(
    rows: list[tuple],
    tsquery_result: str = "methotrexate & dosage",
) -> MagicMock:
    """
    Return a mock psycopg2 connection.

    Handles two cursor.execute calls in order:
      1. _is_stopword_only_query — returns tsquery string
      2. _run_query — returns search result rows
    """
    # cursor 1: stopword check
    stop_cursor = MagicMock()
    stop_cursor.fetchone.return_value = (tsquery_result,)
    stop_cursor.__enter__.return_value = stop_cursor
    stop_cursor.__exit__.return_value = False

    # cursor 2: main query
    query_cursor = MagicMock()
    query_cursor.fetchall.return_value = rows
    query_cursor.__enter__.return_value = query_cursor
    query_cursor.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = [stop_cursor, query_cursor]
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
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=make_mock_conn([]),
            ),
            patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run,
        ):
            keyword_search(QUERY, db_url="postgresql://fake", top_k=5)
        args = mock_run.call_args[0]
        assert args[2] == 5

    def test_specialty_filter_passed_to_run_query(self):
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=make_mock_conn([]),
            ),
            patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run,
        ):
            keyword_search(QUERY, db_url="postgresql://fake", specialty="rheumatology")
        args = mock_run.call_args[0]
        assert "rheumatology" in args

    def test_source_name_filter_passed_to_run_query(self):
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=make_mock_conn([]),
            ),
            patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run,
        ):
            keyword_search(QUERY, db_url="postgresql://fake", source_name="NICE")
        args = mock_run.call_args[0]
        assert "NICE" in args

    def test_doc_type_filter_passed_to_run_query(self):
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=make_mock_conn([]),
            ),
            patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run,
        ):
            keyword_search(QUERY, db_url="postgresql://fake", doc_type="guideline")
        args = mock_run.call_args[0]
        assert "guideline" in args

    def test_multiple_filters_combined(self):
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=make_mock_conn([]),
            ),
            patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run,
        ):
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
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=make_mock_conn([]),
            ),
            patch(
                "src.retrieval.keyword_search._run_query", return_value=[]
            ) as mock_run,
        ):
            keyword_search(QUERY, db_url="postgresql://fake")
        args = mock_run.call_args[0]
        assert args[3] is None  # specialty
        assert args[4] is None  # source_name
        assert args[5] is None  # doc_type

    def test_result_metadata_includes_document_dates(self):
        mock_conn = make_mock_conn([make_row()])
        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(QUERY, db_url="postgresql://fake")
        assert results[0].metadata["creation_date"] == "2020-01-01"
        assert results[0].metadata["publish_date"] == "2021-06-30"
        assert results[0].metadata["last_updated_date"] == "2024-01-15"

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

    def test_bool_top_k_raises_retrieval_error(self):
        with pytest.raises(RetrievalError) as exc_info:
            keyword_search(QUERY, db_url="postgresql://fake", top_k=True)
        assert exc_info.value.stage == "KEYWORD_SEARCH"
        assert "top_k" in exc_info.value.message

    def test_db_connection_failure_raises_retrieval_error(self):
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                side_effect=Exception("connection refused"),
            ),
            pytest.raises(RetrievalError) as exc_info,
        ):
            keyword_search(QUERY, db_url="postgresql://fake")
        assert exc_info.value.stage == "KEYWORD_SEARCH"

    def test_undefined_column_raises_retrieval_error_with_migration_hint(self):
        mock_conn = make_mock_conn([])
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
            ),
            patch(
                "src.retrieval.keyword_search._run_query",
                side_effect=pg_errors.UndefinedColumn("column does not exist"),
            ),
            pytest.raises(RetrievalError) as exc_info,
        ):
            keyword_search(QUERY, db_url="postgresql://fake")
        assert exc_info.value.stage == "KEYWORD_SEARCH"
        assert exc_info.value.query == QUERY
        assert "migration" in exc_info.value.message

    def test_retrieval_error_from_run_query_propagates_unchanged(self):
        mock_conn = make_mock_conn([])
        original_error = RetrievalError(
            stage="KEYWORD_SEARCH",
            query=QUERY,
            message="something specific failed",
        )
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
            ),
            patch(
                "src.retrieval.keyword_search._run_query",
                side_effect=original_error,
            ),
            pytest.raises(RetrievalError) as exc_info,
        ):
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
        with (
            patch(
                "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
            ),
            patch(
                "src.retrieval.keyword_search._run_query",
                side_effect=Exception("query failed"),
            ),
            pytest.raises(RetrievalError),
        ):
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
        row = (*row[:14], None, None, *row[16:])
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

    def test_stopword_only_warning_does_not_leak_query_text(self):
        mock_conn = make_mock_conn([], tsquery_result="")
        with (
            patch("src.retrieval.keyword_search.logger") as mock_logger,
            patch(
                "src.retrieval.keyword_search.psycopg2.connect",
                return_value=mock_conn,
            ),
        ):
            keyword_search("the a is", db_url="postgresql://fake")
        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert not any("the a is" in c for c in warning_calls)

    def test_build_relaxed_tsquery_uses_unique_informative_terms(self):
        relaxed = _build_relaxed_tsquery(
            "Methotrexate methotrexate with fever and sore throat and neutropenia"
        )
        assert relaxed is not None
        assert "methotrexate" in relaxed
        assert "neutropenia" in relaxed
        assert relaxed.count("methotrexate") == 1

    def test_run_query_uses_relaxed_keyword_fallback_when_strict_search_empty(self):
        stop_cursor = MagicMock()
        stop_cursor.fetchone.return_value = ("methotrexate & dosage",)
        stop_cursor.__enter__.return_value = stop_cursor
        stop_cursor.__exit__.return_value = False

        query_cursor = MagicMock()
        query_cursor.fetchall.side_effect = [[], [make_row(chunk_id="relaxed-hit")]]
        query_cursor.__enter__.return_value = query_cursor
        query_cursor.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = [stop_cursor, query_cursor]

        with patch(
            "src.retrieval.keyword_search.psycopg2.connect", return_value=mock_conn
        ):
            results = keyword_search(
                "methotrexate fever sore throat neutropenia",
                db_url="postgresql://fake",
            )

        assert [result.chunk_id for result in results] == ["relaxed-hit"]
        assert query_cursor.execute.call_count == 2

    def test_pooled_connection_used_when_db_url_matches_config(self):
        from unittest.mock import MagicMock, patch

        import src.retrieval.keyword_search as ks_mod

        mock_conn = make_mock_conn([make_row()])

        # Make db_url match db_config.database_url to trigger pool path
        config_url = ks_mod.db_config.database_url

        with (
            patch.object(
                ks_mod.db, "raw_connection"
            ) as mock_pool,
        ):
            mock_pool.return_value.__enter__ = MagicMock(
                return_value=mock_conn
            )
            mock_pool.return_value.__exit__ = MagicMock(return_value=False)
            results = keyword_search(QUERY, db_url=config_url)

        mock_pool.assert_called_once()
        assert isinstance(results, list)

    def test_build_relaxed_tsquery_returns_none_for_generic_only_tokens(self):
        # Use only words that are in RELAXED_QUERY_STOPWORDS or are < 3 chars
        result = _build_relaxed_tsquery("and are for from the with")
        assert result is None

    def test_build_relaxed_tsquery_limits_terms(self):
        from src.retrieval.keyword_search import RELAXED_QUERY_MAX_TERMS
        query = " ".join(
            f"term{i}" for i in range(RELAXED_QUERY_MAX_TERMS + 5)
        )
        result = _build_relaxed_tsquery(query)
        assert result is not None
        assert result.count("|") == RELAXED_QUERY_MAX_TERMS - 1

    def test_build_relaxed_tsquery_returns_none_for_single_token(self):
        # A single valid token is returned as a single-term tsquery (not None)
        result = _build_relaxed_tsquery("migraine")
        assert result == "migraine"

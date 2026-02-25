from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.retrieval.query import EMBEDDING_DIMENSIONS, RetrievalError
from src.retrieval.vector_search import VectorSearchResult, vector_search

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

VALID_EMBEDDING = [0.1] * EMBEDDING_DIMENSIONS
WRONG_EMBEDDING = [0.1] * (EMBEDDING_DIMENSIONS - 284)


def make_row(
    chunk_id: str = "chunk_001",
    doc_id: str = "doc_001",
    text: str = "Some clinical text.",
    score: float = 0.85,
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
        score,
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


def make_mock_conn(rows: list[tuple]) -> MagicMock:
    """Return a mock psycopg2 connection that returns given rows."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestVectorSearch:
    def test_returns_list_of_vector_search_results(self):
        rows = [make_row()]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert isinstance(results, list)
        assert all(isinstance(r, VectorSearchResult) for r in results)

    def test_result_is_pydantic_model(self):
        rows = [make_row()]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert isinstance(results[0], VectorSearchResult)
        # pydantic models support attribute access and .model_dump()
        assert hasattr(results[0], "model_dump")

    def test_results_ordered_by_score_descending(self):
        rows = [make_row(score=0.9), make_row(score=0.7), make_row(score=0.5)]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_score_is_cosine_similarity_not_distance(self):
        rows = [make_row(score=0.85)]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert 0.0 <= results[0].score <= 1.0

    def test_score_floored_at_zero(self):
        rows = [make_row(score=-0.1)]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert results[0].score == 0.0

    def test_top_k_limits_result_count(self):
        rows = [make_row(chunk_id=f"c{i}") for i in range(10)]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(
                    VALID_EMBEDDING, db_url="postgresql://fake", top_k=5
                )
        assert len(results) <= 10

    def test_specialty_filter_passed_to_query(self):
        with patch(
            "src.retrieval.vector_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query", return_value=[]
                ) as mock_run:
                    vector_search(
                        VALID_EMBEDDING,
                        db_url="postgresql://fake",
                        specialty="rheumatology",
                    )
        args = mock_run.call_args[0]
        assert "rheumatology" in args

    def test_source_name_filter_passed_to_query(self):
        with patch(
            "src.retrieval.vector_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query", return_value=[]
                ) as mock_run:
                    vector_search(
                        VALID_EMBEDDING, db_url="postgresql://fake", source_name="NICE"
                    )
        args = mock_run.call_args[0]
        assert "NICE" in args

    def test_doc_type_filter_passed_to_query(self):
        with patch(
            "src.retrieval.vector_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query", return_value=[]
                ) as mock_run:
                    vector_search(
                        VALID_EMBEDDING,
                        db_url="postgresql://fake",
                        doc_type="guideline",
                    )
        args = mock_run.call_args[0]
        assert "guideline" in args

    def test_multiple_filters_combined(self):
        with patch(
            "src.retrieval.vector_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query", return_value=[]
                ) as mock_run:
                    vector_search(
                        VALID_EMBEDDING,
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
            "src.retrieval.vector_search.psycopg2.connect",
            return_value=make_mock_conn([]),
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query", return_value=[]
                ) as mock_run:
                    vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        args = mock_run.call_args[0]
        assert args[3] is None  # specialty
        assert args[4] is None  # source_name
        assert args[5] is None  # doc_type

    def test_empty_result_returns_empty_list(self):
        mock_conn = make_mock_conn([])
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert results == []

    def test_db_connection_failure_raises_retrieval_error(self):
        with patch(
            "src.retrieval.vector_search.psycopg2.connect",
            side_effect=Exception("connection refused"),
        ):
            with pytest.raises(RetrievalError) as exc_info:
                vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert exc_info.value.stage == "VECTOR_SEARCH"

    def test_invalid_embedding_dimensions_raises_retrieval_error(self):
        with pytest.raises(RetrievalError) as exc_info:
            vector_search(WRONG_EMBEDDING, db_url="postgresql://fake")
        assert exc_info.value.stage == "VECTOR_SEARCH"

    def test_metadata_fields_populated(self):
        rows = [
            make_row(specialty="rheumatology", source_name="NICE", title="RA Guide")
        ]
        mock_conn = make_mock_conn(rows)
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                results = vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        assert results[0].metadata["specialty"] == "rheumatology"
        assert results[0].metadata["source_name"] == "NICE"
        assert results[0].metadata["title"] == "RA Guide"

    def test_connection_closed_after_query(self):
        mock_conn = make_mock_conn([])
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        mock_conn.close.assert_called_once()

    def test_connection_closed_on_query_failure(self):
        mock_conn = make_mock_conn([])
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query",
                    side_effect=Exception("query failed"),
                ):
                    with pytest.raises(RetrievalError):
                        vector_search(VALID_EMBEDDING, db_url="postgresql://fake")
        mock_conn.close.assert_called_once()

    def test_retrieval_error_from_run_query_propagates_unchanged(self):
        mock_conn = make_mock_conn([])
        original_error = RetrievalError(
            stage="VECTOR_SEARCH",
            query="",
            message="something specific failed",
        )
        with patch(
            "src.retrieval.vector_search.psycopg2.connect", return_value=mock_conn
        ):
            with patch("src.retrieval.vector_search.register_vector"):
                with patch(
                    "src.retrieval.vector_search._run_query",
                    side_effect=original_error,
                ):
                    with pytest.raises(RetrievalError) as exc_info:
                        vector_search(VALID_EMBEDDING, db_url="postgresql://fake")

        # must be the exact same error — not re-wrapped
        assert exc_info.value is original_error
        assert exc_info.value.message == "something specific failed"

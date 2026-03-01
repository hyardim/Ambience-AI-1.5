from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from src.retrieval.citation import Citation, CitedResult
from src.retrieval.cli import main
from src.retrieval.query import RetrievalError

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def make_cited_result(chunk_id: str = "c1") -> CitedResult:
    return CitedResult(
        chunk_id=chunk_id,
        text="Urate-lowering therapy should be offered to patients with gout.",
        rerank_score=0.94,
        rrf_score=0.03,
        vector_score=0.85,
        keyword_rank=0.72,
        citation=Citation(
            title="Gout: diagnosis and management",
            source_name="NICE",
            specialty="rheumatology",
            doc_type="guideline",
            section_path=["Treatment", "Urate-lowering therapy"],
            section_title="Urate-lowering therapy",
            page_start=12,
            page_end=13,
            source_url="https://www.nice.org.uk/guidance/cg56",
            doc_id="doc_001",
            chunk_id=chunk_id,
            content_type="text",
        ),
    )


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


class TestCLI:
    def setup_method(self):
        self.runner = CliRunner()

    def test_query_command_calls_retrieve(self):
        with patch(
            "src.retrieval.cli.retrieve", return_value=[make_cited_result()]
        ) as mock_retrieve:
            result = self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/test",
                ],
            )
        assert result.exit_code == 0
        mock_retrieve.assert_called_once()

    def test_missing_db_url_exits_with_code_1(self):
        with patch("src.retrieval.cli._resolve_db_url", return_value=None):
            result = self.runner.invoke(
                main,
                ["query", "--query", "gout treatment"],
            )
        assert result.exit_code == 1

    def test_no_results_exits_with_code_2(self):
        with patch("src.retrieval.cli.retrieve", return_value=[]):
            result = self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/test",
                ],
            )
        assert result.exit_code == 2

    def test_retrieval_error_exits_with_code_1(self):
        with patch(
            "src.retrieval.cli.retrieve",
            side_effect=RetrievalError(
                stage="RERANK", query="gout treatment", message="model failed"
            ),
        ):
            result = self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/test",
                ],
            )
        assert result.exit_code == 1

    def test_output_contains_score_and_citation(self):
        with patch("src.retrieval.cli.retrieve", return_value=[make_cited_result()]):
            result = self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/test",
                ],
            )
        assert "0.94" in result.output
        assert "NICE" in result.output
        assert "rheumatology" in result.output

    def test_expand_query_flag_passed_to_retrieve(self):
        with patch(
            "src.retrieval.cli.retrieve", return_value=[make_cited_result()]
        ) as mock_retrieve:
            self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/test",
                    "--expand-query",
                ],
            )
        _, kwargs = mock_retrieve.call_args
        assert kwargs["expand_query"] is True

    def test_write_debug_artifacts_flag_passed_to_retrieve(self):
        with patch(
            "src.retrieval.cli.retrieve", return_value=[make_cited_result()]
        ) as mock_retrieve:
            self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/test",
                    "--write-debug-artifacts",
                ],
            )
        _, kwargs = mock_retrieve.call_args
        assert kwargs["write_debug_artifacts"] is True

    def test_main_entrypoint_is_callable(self):
        result = self.runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_db_url_resolved_from_environment_variable(self):
        with (
            patch.dict(
                "os.environ", {"DATABASE_URL": "postgresql://localhost/env_test"}
            ),
            patch(
                "src.retrieval.cli.retrieve", return_value=[make_cited_result()]
            ) as mock_retrieve,
        ):
            result = self.runner.invoke(
                main,
                ["query", "--query", "gout treatment"],
            )
        assert result.exit_code == 0
        _, kwargs = mock_retrieve.call_args
        assert kwargs["db_url"] == "postgresql://localhost/env_test"

    def test_db_url_resolved_from_dotenv_file(self):
        call_count = {"n": 0}

        def env_get(key: str, *args: object) -> str | None:
            if key == "DATABASE_URL":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    return None
                return "postgresql://localhost/dotenv_test"
            return None

        with (
            patch("src.retrieval.cli.os.environ.get", side_effect=env_get),
            patch("src.retrieval.cli.load_dotenv") as mock_load_dotenv,
            patch(
                "src.retrieval.cli.retrieve", return_value=[make_cited_result()]
            ) as mock_retrieve,
        ):
            result = self.runner.invoke(
                main,
                ["query", "--query", "gout treatment"],
            )
        assert result.exit_code == 0
        mock_load_dotenv.assert_called_once()
        _, kwargs = mock_retrieve.call_args
        assert kwargs["db_url"] == "postgresql://localhost/dotenv_test"

    def test_db_url_flag_takes_precedence_over_env(self):
        with (
            patch.dict(
                "os.environ", {"DATABASE_URL": "postgresql://localhost/env_test"}
            ),
            patch(
                "src.retrieval.cli.retrieve", return_value=[make_cited_result()]
            ) as mock_retrieve,
        ):
            result = self.runner.invoke(
                main,
                [
                    "query",
                    "--query",
                    "gout treatment",
                    "--db-url",
                    "postgresql://localhost/flag_test",
                ],
            )
        assert result.exit_code == 0
        _, kwargs = mock_retrieve.call_args
        assert kwargs["db_url"] == "postgresql://localhost/flag_test"

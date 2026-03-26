from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from src.retrieval.query import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    ProcessedQuery,
    RetrievalError,
    _expand_query,
    process_query,
)

# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

MOCK_EMBEDDING = np.array([[0.1] * EMBEDDING_DIMENSIONS], dtype=np.float32)


def _make_mock_model(embedding: np.ndarray = MOCK_EMBEDDING) -> MagicMock:
    """Return a mock SentenceTransformer that returns a fixed embedding."""
    mock = MagicMock()
    mock.encode.return_value = embedding
    return mock


# -----------------------------------------------------------------------
# Tests — process_query()
# -----------------------------------------------------------------------


class TestProcessQuery:
    def test_returns_processed_query_pydantic_model(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment")
        assert isinstance(result, ProcessedQuery)

    def test_embedding_has_correct_dimensions(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment")
        assert len(result.embedding) == EMBEDDING_DIMENSIONS

    def test_empty_query_raises_value_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            process_query("")

    def test_whitespace_only_query_raises_value_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            process_query("   ")

    def test_expand_false_leaves_query_unchanged(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment", expand=False)
        assert result.expanded == result.original

    def test_expand_true_appends_synonyms(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment", expand=True)
        assert "urate" in result.expanded
        assert "hyperuricemia" in result.expanded
        assert "uric acid" in result.expanded

    def test_expand_true_preserves_original_terms(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment", expand=True)
        assert "gout" in result.expanded
        assert "treatment" in result.expanded

    def test_unknown_term_expansion_leaves_query_unchanged(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("fibromyalgia management", expand=True)
        assert result.expanded == "fibromyalgia management"

    def test_embedding_model_name_recorded_in_output(self):
        mock_model = _make_mock_model()
        with patch("src.retrieval.query._load_model", return_value=mock_model):
            result = process_query("gout treatment")
        assert result.embedding_model == EMBEDDING_MODEL_NAME

    def test_process_query_wraps_model_load_failure_as_retrieval_error(self):
        with (
            patch(
                "src.retrieval.query._load_model",
                side_effect=RuntimeError("model not found"),
            ),
            pytest.raises(RetrievalError) as exc_info,
        ):
            process_query("gout treatment")
        assert exc_info.value.stage == "QUERY"

    def test_embedding_failure_raises_retrieval_error(self):
        mock_model = _make_mock_model()
        mock_model.encode.side_effect = RuntimeError("CUDA out of memory")
        with (
            patch("src.retrieval.query._load_model", return_value=mock_model),
            pytest.raises(RetrievalError) as exc_info,
        ):
            process_query("gout treatment")
        assert exc_info.value.stage == "QUERY"

    def test_wrong_embedding_dimensions_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ProcessedQuery(
                original="test",
                expanded="test",
                embedding=[0.1] * (EMBEDDING_DIMENSIONS - 1),  # one short
                embedding_model="some-model",
            )

    def test_query_exceeding_token_limit_raises_value_error(self):
        long_query = " ".join(["gout"] * 2000)
        with (
            patch("src.retrieval.query.embed_config.query_max_tokens", 32),
            pytest.raises(ValueError, match="exceeds 32 token limit"),
        ):
            process_query(long_query)

    def test_expanded_query_exceeding_token_limit_raises_value_error(self):
        # Patch _expand_query to return a very long string
        # simulating expansion pushing query over the limit
        long_expansion = "gout " + " ".join(["urate"] * 400)
        mock_model = _make_mock_model()
        with (
            patch("src.retrieval.query.embed_config.query_max_tokens", 32),
            patch("src.retrieval.query._load_model", return_value=mock_model),
            patch("src.retrieval.query._expand_query", return_value=long_expansion),
            pytest.raises(ValueError, match="exceeds 32 token limit"),
        ):
            process_query("gout", expand=True)

    def test_invalid_embedding_wraps_as_retrieval_error(self):
        # Force _embed to return wrong dimensions so ProcessedQuery construction fails
        mock_model = _make_mock_model(
            embedding=np.array([[0.1] * 100], dtype=np.float32)  # wrong dims
        )
        with (
            patch("src.retrieval.query._load_model", return_value=mock_model),
            pytest.raises(RetrievalError) as exc_info,
        ):
            process_query("gout treatment")
        assert exc_info.value.stage == "QUERY"

    def test_token_length_uses_shared_counter(self):
        mock_model = _make_mock_model()
        with (
            patch("src.retrieval.query.count_tokens", return_value=99),
            patch("src.retrieval.query.embed_config.query_max_tokens", 32),
            patch("src.retrieval.query._load_model", return_value=mock_model),
            pytest.raises(ValueError, match="exceeds 32 token limit"),
        ):
            process_query("gout treatment")


# -----------------------------------------------------------------------
# Tests — _load_model()
# -----------------------------------------------------------------------


class TestLoadModel:
    def test_load_model_uses_shared_ingestion_cache(self):
        with patch("src.retrieval.query.load_embedder") as mock_load_embedder:
            mock_load_embedder.return_value = MagicMock()
            from src.retrieval.query import _load_model

            result = _load_model()

        mock_load_embedder.assert_called_once_with(model_name=EMBEDDING_MODEL_NAME)
        assert result is not None


# -----------------------------------------------------------------------
# Tests — _expand_query()
# -----------------------------------------------------------------------


class TestExpandQuery:
    def test_gout_expansion(self):
        result = _expand_query("gout")
        assert "urate" in result
        assert "hyperuricemia" in result
        assert "uric acid" in result

    def test_ra_expansion(self):
        result = _expand_query("RA treatment")
        assert "rheumatoid arthritis" in result

    def test_oa_expansion(self):
        result = _expand_query("OA management")
        assert "osteoarthritis" in result

    def test_no_duplicate_synonyms_added(self):
        result = _expand_query("gout urate management")
        assert result.count("urate") == 1

    def test_unknown_term_returns_original(self):
        query = "fibromyalgia management"
        result = _expand_query(query)
        assert result == query

    def test_overlapping_expansions_do_not_produce_duplicates(self):
        # both "dmard" and "methotrexate" map to "disease modifying antirheumatic drug"
        result = _expand_query("methotrexate dmard dosage")
        assert result.count("disease modifying antirheumatic drug") == 1

    def test_new_medical_abbreviation_expansion(self):
        result = _expand_query("GCA headache")
        assert "giant cell arteritis" in result

    def test_aspirin_expansion(self):
        result = _expand_query("aspirin management")
        assert "acetylsalicylic acid" in result

    def test_red_flag_back_pain_cluster_expands_to_cauda_equina(self):
        result = _expand_query(
            "Severe back pain with bilateral leg weakness and urinary retention."
        )
        assert "cauda equina syndrome" in result
        assert "progressive neurological deficit" in result

    def test_nph_pattern_expands_to_normal_pressure_hydrocephalus(self):
        result = _expand_query(
            "Gait disturbance with urinary incontinence and ventriculomegaly."
        )
        assert "normal pressure hydrocephalus" in result
        assert "NPH" in result
        assert "gait apraxia" in result

    def test_visual_headache_pattern_expands_to_migraine_aura_and_tia(self):
        result = _expand_query(
            "Transient visual disturbance followed by headache for 10 minutes."
        )
        assert "migraine aura" in result
        assert "transient ischaemic attack" in result

    def test_migraine_tia_comparison_expansion_adds_balanced_comparison_terms(self):
        result = _expand_query(
            "How can migraine aura be distinguished from TIA in primary care?"
        )
        assert "migraine aura" in result
        assert "transient ischaemic attack" in result
        assert "positive visual symptoms" in result
        assert "sudden negative symptoms" in result

    def test_methotrexate_toxicity_pattern_expands_to_monitoring_terms(self):
        result = _expand_query(
            "Methotrexate with fever, sore throat, and neutropenia on blood count."
        )
        assert "DMARD toxicity" in result
        assert "drug-induced neutropenia" in result
        assert "csDMARD monitoring" in result

    def test_sle_renal_pattern_expands_to_lupus_nephritis_terms(self):
        result = _expand_query(
            "Known SLE with new proteinuria and rising creatinine."
        )
        assert "lupus nephritis" in result
        assert "renal involvement" in result
        assert "nephrology referral" in result

    def test_inflammatory_arthritis_referral_pattern_expands_to_triage_terms(self):
        result = _expand_query(
            "Intermittent joint swelling in knees and wrists before "
            "specialist referral."
        )
        assert "early inflammatory arthritis" in result
        assert "baseline blood tests" in result
        assert "plain radiographs" in result


# -----------------------------------------------------------------------
# Tests — RetrievalError
# -----------------------------------------------------------------------


class TestRetrievalError:
    def test_retrieval_error_has_stage(self):
        err = RetrievalError(stage="QUERY", query="test", message="something failed")
        assert err.stage == "QUERY"

    def test_retrieval_error_has_query(self):
        err = RetrievalError(stage="QUERY", query="test query", message="failed")
        assert err.query == "test query"

    def test_retrieval_error_str_includes_stage_and_query(self):
        err = RetrievalError(stage="QUERY", query="test", message="failed")
        assert "QUERY" in str(err)
        assert "test" in str(err)


class TestExpandRedFlagPatternsEarlyReturn:
    """Cover the early-return in _expand_red_flag_patterns (line 300)."""

    def test_migraine_tia_comparison_returns_query_unchanged_when_all_terms_present(self):
        """When the query already contains every balanced comparison term,
        _balanced_migraine_tia_comparison_terms returns [] and the original
        query is returned unchanged via the early-return path."""
        from src.retrieval.query import expand_query_text

        # Craft a query that (a) triggers _is_migraine_tia_comparison_query and
        # (b) already contains ALL synonyms that _balanced_migraine_tia_comparison_terms
        # would normally add, so the additions list is empty.
        full_query = (
            "distinguish migraine aura transient ischaemic attack "
            "positive visual symptoms gradual spread fully reversible "
            "5 to 60 minutes sudden negative symptoms"
        )
        result = expand_query_text(full_query)
        # The result should equal the original because nothing was added.
        assert result == full_query

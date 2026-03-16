import src.generation.router as router
from src.generation.router import (
    _score_ambiguity,
    _score_complexity,
    select_generation_provider,
)


def test_select_generation_provider_routes_simple_queries_local() -> None:
    decision = select_generation_provider(
        query="What is migraine?",
        retrieved_chunks=[{"score": 0.72}, {"score": 0.55}, {"score": 0.49}],
    )

    assert decision.provider == "local"
    assert decision.score < decision.threshold


def test_select_generation_provider_routes_risky_queries_cloud() -> None:
    decision = select_generation_provider(
        query=(
            "A patient has sudden vision loss and progressive weakness. "
            "What investigations and urgent management steps are recommended?"
        ),
        retrieved_chunks=[{"score": 0.33}, {"score": 0.31}, {"score": 0.29}],
        severity="urgent",
    )

    assert decision.provider == "cloud"
    assert decision.score >= decision.threshold
    assert "severity_urgent" in decision.reasons


def test_select_generation_provider_routes_revisions_cloud() -> None:
    decision = select_generation_provider(
        query="Please revise the treatment plan.",
        retrieved_chunks=[{"score": 0.61}, {"score": 0.59}],
        is_revision=True,
    )

    assert decision.provider == "cloud"
    assert "revision_flow" in decision.reasons


def test_select_generation_provider_force_cloud(monkeypatch) -> None:
    monkeypatch.setattr(router, "FORCE_CLOUD_LLM", True)

    decision = select_generation_provider(query="q", retrieved_chunks=[])

    assert decision.provider == "cloud"
    assert decision.reasons == ("force_cloud_llm",)


def test_select_generation_provider_scores_ambiguity_and_complexity() -> None:
    decision = select_generation_provider(
        query="Compare investigations. Another sentence! Third sentence?",
        retrieved_chunks=[{"score": 0.34}, {"score": 0.33}],
    )

    assert "multi_sentence" in decision.reasons
    assert "complex_reasoning_terms" in decision.reasons
    assert "low_top_score" in decision.reasons
    assert "small_top_gap" in decision.reasons


def test_select_generation_provider_scores_emergency_severity() -> None:
    decision = select_generation_provider(
        query="Acute issue",
        retrieved_chunks=[{"score": 0.9}, {"score": 0.5}, {"score": 0.49}],
        severity="emergency",
    )

    assert "severity_emergency" in decision.reasons


def test_score_complexity_medium_query_reason() -> None:
    query = "x" * 150

    score, reasons = _score_complexity(query)

    assert score > 0
    assert "medium_query" in reasons


def test_score_complexity_long_query_reason() -> None:
    query = "x" * 250

    score, reasons = _score_complexity(query)

    assert score > 0
    assert "long_query" in reasons


def test_score_ambiguity_no_hits() -> None:
    score, reasons = _score_ambiguity([])

    assert score == 0.22
    assert reasons == ["no_retrieval_hits"]


def test_score_ambiguity_moderate_branches() -> None:
    score, reasons = _score_ambiguity(
        [{"score": 0.4}, {"score": 0.35}, {"score": 0.2}]
    )

    assert score > 0
    assert "moderate_top_score" in reasons
    assert "moderate_top_gap" in reasons

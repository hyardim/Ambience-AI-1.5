import src.generation.router as router
from src.generation.router import select_generation_provider


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

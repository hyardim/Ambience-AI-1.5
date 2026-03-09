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

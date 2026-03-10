from src.generation.router import select_generation_provider


def test_router_prefers_cloud_for_complex_risky_query() -> None:
    query = (
        "Provide a differential diagnosis and stepwise management plan for sudden "
        "progressive bilateral vision loss with confusion and possible vasculitis."
    )
    retrieved = [
        {"score": 0.31},
        {"score": 0.30},
        {"score": 0.28},
    ]

    decision = select_generation_provider(
        query=query,
        retrieved_chunks=retrieved,
        severity="urgent",
        threshold=0.65,
    )

    assert decision.provider == "cloud"
    assert decision.score >= decision.threshold


def test_router_prefers_local_for_simple_query_with_strong_retrieval() -> None:
    decision = select_generation_provider(
        query="What is rheumatoid arthritis?",
        retrieved_chunks=[{"score": 0.74}, {"score": 0.62}, {"score": 0.59}],
        severity=None,
        threshold=0.65,
    )

    assert decision.provider == "local"
    assert decision.score < decision.threshold


def test_router_forces_cloud_for_revision_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr("src.generation.router.ROUTE_REVISIONS_TO_CLOUD", True)

    decision = select_generation_provider(
        query="Short follow-up query",
        retrieved_chunks=[{"score": 0.8}],
        is_revision=True,
        threshold=0.65,
    )

    assert decision.provider == "cloud"
    assert "revision_flow" in decision.reasons

from src.generation import router


def test_select_generation_provider_no_hits_includes_ambiguity_reason():
    decision = router.select_generation_provider(query="test", retrieved_chunks=[])
    assert "no_retrieval_hits" in decision.reasons


def test_select_generation_provider_high_confidence_simple_stays_local():
    decision = router.select_generation_provider(
        query="Simple question about migraine",
        retrieved_chunks=[{"score": 0.9}, {"score": 0.5}],
    )
    assert decision.provider == "local"
    assert decision.score < decision.threshold


def test_select_generation_provider_force_cloud(monkeypatch):
    monkeypatch.setattr(router, "FORCE_CLOUD_LLM", True)
    decision = router.select_generation_provider(
        query="any", retrieved_chunks=[{"score": 0.1}]
    )
    assert decision.provider == "cloud"
    assert "force_cloud_llm" in decision.reasons

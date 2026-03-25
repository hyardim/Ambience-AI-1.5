import pytest


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch):
    """Bypass API-key auth for tests by clearing the key and marking test env."""
    monkeypatch.delenv("RAG_INTERNAL_API_KEY", raising=False)
    monkeypatch.setenv("RAG_ENV", "test")

from __future__ import annotations

import sys
import types

import pytest

from src.api import startup


@pytest.fixture(autouse=True)
def clear_embedding_caches() -> None:
    startup.get_embedding_model.cache_clear()
    startup.get_embedding_dimension.cache_clear()


def test_ensure_schema_initializes_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup, "get_embedding_dimension", lambda: 384)
    called: list[int] = []
    monkeypatch.setattr(
        startup,
        "init_db",
        lambda vector_dim: called.append(vector_dim),
    )

    startup.ensure_schema()

    assert called == [384]


def test_ensure_schema_raises_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup, "get_embedding_dimension", lambda: 384)

    def boom(vector_dim: int) -> None:
        raise RuntimeError(f"bad dim {vector_dim}")

    monkeypatch.setattr(startup, "init_db", boom)

    with pytest.raises(RuntimeError, match="Database schema initialization failed"):
        startup.ensure_schema()


@pytest.mark.anyio
async def test_warmup_ollama_cloud_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.routing_config, "force_cloud_llm", True)
    calls: list[str] = []

    async def fake_warmup(provider: str = "local") -> None:
        calls.append(provider)

    monkeypatch.setattr(startup, "warmup_model", fake_warmup)

    await startup.warmup_ollama()

    assert calls == ["cloud"]


@pytest.mark.anyio
async def test_warmup_ollama_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(startup.routing_config, "force_cloud_llm", False)
    calls: list[str] = []

    async def fake_warmup(provider: str = "local") -> None:
        calls.append(provider)

    monkeypatch.setattr(startup, "warmup_model", fake_warmup)

    await startup.warmup_ollama()

    assert calls == ["local"]


def test_get_embedding_model_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_load_embedder() -> object:
        calls.append("load")
        return object()

    monkeypatch.setattr(startup, "load_embedder", fake_load_embedder)
    monkeypatch.setattr(startup, "get_vector_dim", lambda model: 384)

    first = startup.get_embedding_model()
    second = startup.get_embedding_model()

    assert first is second
    assert calls == ["load"]


def test_get_embedding_dimension_uses_model(monkeypatch: pytest.MonkeyPatch) -> None:
    model = object()
    monkeypatch.setattr(startup, "get_embedding_model", lambda: model)
    monkeypatch.setattr(
        startup,
        "get_vector_dim",
        lambda loaded: 768 if loaded is model else 0,
    )

    assert startup.get_embedding_dimension() == 768


@pytest.mark.anyio
async def test_lifespan_runs_startup_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        startup,
        "validate_internal_api_key_config",
        lambda: calls.append("validate"),
    )
    monkeypatch.setattr(
        startup,
        "get_embedding_dimension",
        lambda: calls.append("dim") or 384,
    )
    monkeypatch.setattr(startup, "ensure_schema", lambda: calls.append("schema"))

    async def fake_warmup() -> None:
        calls.append("warmup")

    monkeypatch.setattr(startup, "warmup_ollama", fake_warmup)

    async with startup.lifespan(object()):  # type: ignore[arg-type]
        calls.append("inside")

    assert calls == ["validate", "dim", "schema", "warmup", "inside"]


def test_validate_internal_api_key_config_production_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "")

    with pytest.raises(RuntimeError, match="RAG_INTERNAL_API_KEY"):
        startup.validate_internal_api_key_config()


def test_validate_internal_api_key_config_production_rejects_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "dev-rag-internal-key")

    with pytest.raises(RuntimeError, match="RAG_INTERNAL_API_KEY"):
        startup.validate_internal_api_key_config()


def test_validate_internal_api_key_config_allows_custom_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("RAG_INTERNAL_API_KEY", "super-strong-internal-key")

    startup.validate_internal_api_key_config()


def test_validate_internal_api_key_config_non_test_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("RAG_INTERNAL_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="RAG_INTERNAL_API_KEY"):
        startup.validate_internal_api_key_config()


@pytest.mark.anyio
async def test_warmup_model_delegates_to_generation_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    fake_module = types.SimpleNamespace()

    async def fake_warmup_model(provider: str = "local") -> None:
        calls.append(provider)

    fake_module.warmup_model = fake_warmup_model
    monkeypatch.setitem(sys.modules, "src.generation.client", fake_module)

    await startup.warmup_model("cloud")

    assert calls == ["cloud"]


def test_load_embedder_delegates_to_ingestion_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = object()
    fake_module = types.SimpleNamespace(load_embedder=lambda: embedder)
    monkeypatch.setitem(sys.modules, "src.ingestion.embed", fake_module)

    assert startup.load_embedder() is embedder


def test_get_vector_dim_delegates_to_ingestion_embed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_module = types.SimpleNamespace(
        get_vector_dim=lambda model: 123 if model else 0
    )
    monkeypatch.setitem(sys.modules, "src.ingestion.embed", fake_module)

    assert startup.get_vector_dim(object()) == 123


def test_init_db_delegates_to_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []
    fake_module = types.SimpleNamespace(
        init_db=lambda *, vector_dim: called.append(vector_dim)
    )
    monkeypatch.setitem(sys.modules, "src.retrieval.vector_store", fake_module)

    startup.init_db(256)

    assert called == [256]


def test_validate_internal_api_key_config_skips_in_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("RAG_INTERNAL_API_KEY", raising=False)

    startup.validate_internal_api_key_config()

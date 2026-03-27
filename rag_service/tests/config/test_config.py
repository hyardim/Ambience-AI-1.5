from pathlib import Path

import pytest

from src.config import (
    ChunkingConfig,
    DatabaseConfig,
    EmbeddingConfig,
    LoggingConfig,
    PathConfig,
    RetrievalConfig,
    VectorIndexConfig,
)


class TestDatabaseConfig:
    def test_default_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POSTGRES_HOST", raising=False)
        monkeypatch.delenv("POSTGRES_PORT", raising=False)
        monkeypatch.delenv("POSTGRES_USER", raising=False)
        monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
        monkeypatch.delenv("POSTGRES_DB", raising=False)
        config = DatabaseConfig()
        assert config.postgres_host == "localhost"
        assert config.postgres_port == 5432
        assert config.postgres_user == "admin"
        assert config.postgres_db == "ambience_knowledge"

    def test_connection_string_format(self) -> None:
        config = DatabaseConfig()
        cs = config.connection_string
        assert cs.startswith("postgresql://")
        assert config.postgres_host in cs
        assert str(config.postgres_port) in cs
        assert config.postgres_db in cs

    def test_connection_string_contains_credentials(self) -> None:
        config = DatabaseConfig()
        assert config.postgres_user in config.connection_string

    def test_connection_string_escapes_special_characters(self) -> None:
        config = DatabaseConfig(
            postgres_user="user+name",
            postgres_password="p@ss word",
        )

        assert "user%2Bname" in config.connection_string
        assert "p%40ss+word" in config.connection_string

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_HOST", "testhost")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        config = DatabaseConfig()
        assert config.postgres_host == "testhost"
        assert config.postgres_port == 5433


class TestEmbeddingConfig:
    def test_default_values(self) -> None:
        config = EmbeddingConfig()
        assert config.embedding_model == "all-MiniLM-L6-v2"
        assert config.embedding_dimension == 384
        assert config.query_max_tokens == 1024
        assert config.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
        monkeypatch.setenv("QUERY_MAX_TOKENS", "2048")
        config = EmbeddingConfig()
        assert config.embedding_dimension == 768
        assert config.query_max_tokens == 2048


class TestChunkingConfig:
    def test_default_values(self) -> None:
        config = ChunkingConfig()
        assert config.chunk_size == 450
        assert config.chunk_overlap == 100

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHUNK_SIZE", "512")
        config = ChunkingConfig()
        assert config.chunk_size == 512


class TestVectorIndexConfig:
    def test_default_values(self) -> None:
        config = VectorIndexConfig()
        assert config.hnsw_m == 16
        assert config.hnsw_ef_construction == 64


class TestLoggingConfig:
    def test_default_values(self) -> None:
        config = LoggingConfig()
        assert config.log_level == "INFO"
        assert config.log_file == "logs/rag.log"


class TestRetrievalConfig:
    def test_default_values(self) -> None:
        config = RetrievalConfig()
        assert config.retrieval_canonicalization_enabled is False
        assert config.retrieval_canonicalization_specialties == "rheumatology"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RETRIEVAL_CANONICALIZATION_ENABLED", "true")
        monkeypatch.setenv(
            "RETRIEVAL_CANONICALIZATION_SPECIALTIES",
            "rheumatology,neurology",
        )
        config = RetrievalConfig()
        assert config.retrieval_canonicalization_enabled is True
        assert config.retrieval_canonicalization_specialties == "rheumatology,neurology"


class TestPathConfig:
    def test_paths_are_path_objects(self) -> None:
        config = PathConfig()
        assert isinstance(config.root, Path)
        assert isinstance(config.data_raw, Path)
        assert isinstance(config.data_processed, Path)
        assert isinstance(config.logs, Path)

    def test_path_structure(self) -> None:
        config = PathConfig()
        assert config.data_raw == config.root / "data" / "raw"
        assert config.data_processed == config.root / "data" / "processed"
        assert config.data_debug == config.root / "data" / "debug"
        assert config.logs == config.root / "logs"

    def test_root_is_resolved_project_path(self) -> None:
        config = PathConfig()
        assert config.root == Path(__file__).resolve().parents[2]

    def test_data_raw_respects_relative_rag_data_dir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAG_DATA_DIR", "custom/raw")
        config = PathConfig()
        assert config.data_raw == config.root / "custom" / "raw"

    def test_data_raw_respects_absolute_rag_data_dir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("RAG_DATA_DIR", "/tmp/ambience-rag-raw")
        config = PathConfig()
        assert config.data_raw == Path("/tmp/ambience-rag-raw")


def test_first_non_empty_returns_first_truthy() -> None:
    from src.config import _first_non_empty

    assert _first_non_empty("", None, "value", "later") == "value"


def test_default_runpod_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import _default_runpod_api_key, _default_runpod_base_url

    monkeypatch.delenv("RUNPOD_POD_ID", raising=False)
    assert _default_runpod_base_url() is None

    monkeypatch.setenv("RUNPOD_POD_ID", "pod123")
    monkeypatch.setenv("RUNPOD_PORT", "9000")
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)

    assert _default_runpod_base_url() == "https://pod123-9000.proxy.runpod.net/v1"
    assert _default_runpod_api_key() == "sk-pod123"


def test_build_local_llm_config_uses_docker_override_in_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.config import build_local_llm_config, generation_config

    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("DOCKER_OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setattr("src.config.llm._running_in_docker", lambda: True)

    config = build_local_llm_config(generation_config)
    assert config.base_url == "http://host.docker.internal:11434"


def test_build_local_llm_config_prefers_explicit_local_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.config import build_local_llm_config, generation_config

    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://custom-local:11434")
    monkeypatch.setenv("DOCKER_OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setattr("src.config.llm._running_in_docker", lambda: True)

    config = build_local_llm_config(generation_config)
    assert config.base_url == "http://custom-local:11434"


def test_cloud_llm_is_configured_rejects_no_scheme_url() -> None:
    from src.config.llm import CloudLLMConfig, cloud_llm_is_configured

    config = CloudLLMConfig(
        base_url="noscheme.example.com/v1",
        api_key="sk-real",
        model="gpt-4",
        max_tokens=1024,
        temperature=0.1,
        timeout_seconds=120.0,
    )
    assert cloud_llm_is_configured(config) is False


def test_cloud_llm_is_configured_rejects_localhost() -> None:
    from src.config.llm import CloudLLMConfig, cloud_llm_is_configured

    config = CloudLLMConfig(
        base_url="http://localhost:8080/v1",
        api_key="sk-real",
        model="gpt-4",
        max_tokens=1024,
        temperature=0.1,
        timeout_seconds=120.0,
    )
    assert cloud_llm_is_configured(config) is False


def test_cloud_llm_is_configured_rejects_placeholder_key() -> None:
    from src.config.llm import CloudLLMConfig, cloud_llm_is_configured

    config = CloudLLMConfig(
        base_url="https://api.real.com/v1",
        api_key="dummy",
        model="gpt-4",
        max_tokens=1024,
        temperature=0.1,
        timeout_seconds=120.0,
    )
    assert cloud_llm_is_configured(config) is False


def test_cloud_llm_is_configured_rejects_required_prefix_key() -> None:
    from src.config.llm import CloudLLMConfig, cloud_llm_is_configured

    config = CloudLLMConfig(
        base_url="https://api.real.com/v1",
        api_key="required_key",
        model="gpt-4",
        max_tokens=1024,
        temperature=0.1,
        timeout_seconds=120.0,
    )
    assert cloud_llm_is_configured(config) is False


def test_cloud_llm_is_configured_accepts_real_config() -> None:
    from src.config.llm import CloudLLMConfig, cloud_llm_is_configured

    config = CloudLLMConfig(
        base_url="https://api.real.com/v1",
        api_key="sk-real-key-123",
        model="gpt-4",
        max_tokens=1024,
        temperature=0.1,
        timeout_seconds=120.0,
    )
    assert cloud_llm_is_configured(config) is True

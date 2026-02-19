from pathlib import Path

import pytest

from src.config import (
    ChunkingConfig,
    DatabaseConfig,
    EmbeddingConfig,
    LoggingConfig,
    PathConfig,
    VectorIndexConfig,
)


class TestDatabaseConfig:
    def test_default_values(self) -> None:
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

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDING_DIMENSION", "768")
        config = EmbeddingConfig()
        assert config.embedding_dimension == 768


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
        assert config.logs == config.root / "logs"

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="admin")
    postgres_password: str = Field(default="password")
    postgres_db: str = Field(default="ambience_knowledge")

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class EmbeddingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)


class ChunkingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    chunk_size: int = Field(default=450)
    chunk_overlap: int = Field(default=100)


class VectorIndexConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    hnsw_m: int = Field(default=16)
    hnsw_ef_construction: int = Field(default=64)


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/rag.log")


class GenerationConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="thewindmom/llama3-med42-8b")
    ollama_max_tokens: int = Field(default=512)


class PathConfig:
    def __init__(self) -> None:
        self.root: Path = Path(__file__).parent.parent
        self.data_raw: Path = self.root / "data" / "raw"
        self.data_processed: Path = self.root / "data" / "processed"
        self.data_debug: Path = self.root / "data" / "debug"
        self.logs: Path = self.root / "logs"


db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
vector_config = VectorIndexConfig()
logging_config = LoggingConfig()
generation_config = GenerationConfig()
path_config = PathConfig()

# Compatibility shims for existing codepaths
DATABASE_URL = db_config.connection_string
MODEL_NAME = embed_config.embedding_model
RAG_DATA_DIR = os.getenv("RAG_DATA_DIR", str(path_config.data_raw))
CHUNK_SIZE = chunk_config.chunk_size
CHUNK_OVERLAP = chunk_config.chunk_overlap
HNSW_M = vector_config.hnsw_m
HNSW_EF_CONSTRUCTION = vector_config.hnsw_ef_construction
OLLAMA_BASE_URL = generation_config.ollama_base_url
OLLAMA_MODEL = generation_config.ollama_model
OLLAMA_MAX_TOKENS = generation_config.ollama_max_tokens
db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
vector_config = VectorIndexConfig()
logging_config = LoggingConfig()
path_config = PathConfig()

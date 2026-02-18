from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="admin")
    postgres_password: str = Field(default="")
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
    )

    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)


class ChunkingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    chunk_size: int = Field(default=450)
    chunk_overlap: int = Field(default=100)


class VectorIndexConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    hnsw_m: int = Field(default=16)
    hnsw_ef_construction: int = Field(default=64)


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/rag.log")


class PathConfig:
    def __init__(self) -> None:
        self.root: Path = Path(__file__).parent.parent
        self.data_raw: Path = self.root / "data" / "raw"
        self.data_processed: Path = self.root / "data" / "processed"
        self.logs: Path = self.root / "logs"


db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
vector_config = VectorIndexConfig()
logging_config = LoggingConfig()
path_config = PathConfig()

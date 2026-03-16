import os
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field

from .base import PROJECT_ROOT, AppBaseSettings


class DatabaseConfig(AppBaseSettings):
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="admin")
    postgres_password: str = Field(default="password")
    postgres_db: str = Field(default="ambience_knowledge")

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql://{quote_plus(self.postgres_user)}:"
            f"{quote_plus(self.postgres_password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", self.connection_string)


class EmbeddingConfig(AppBaseSettings):
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    embedding_dimension: int = Field(default=384)


class ChunkingConfig(AppBaseSettings):
    chunk_size: int = Field(default=450)
    chunk_overlap: int = Field(default=100)


class VectorIndexConfig(AppBaseSettings):
    hnsw_m: int = Field(default=16)
    hnsw_ef_construction: int = Field(default=64)


class PathConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    root: Path = Field(default_factory=lambda: PROJECT_ROOT)

    @property
    def data_raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def data_processed(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def data_debug(self) -> Path:
        return self.root / "data" / "debug"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

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
    ollama_max_tokens: int = Field(default=1024)
    ollama_timeout_seconds: float = Field(default=60.0)


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_base_url: str = Field(default="http://localhost:11434/v1")
    llm_model: str = Field(default="thewindmom/llama3-med42-8b")
    llm_api_key: str = Field(default="ollama")
    llm_max_tokens: int = Field(default=1024)
    llm_temperature: float = Field(default=0.1)
    llm_timeout_seconds: float = Field(default=120.0)


class RoutingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    llm_route_threshold: float = Field(default=0.65)
    route_revisions_to_cloud: bool = Field(default=True)
    force_cloud_llm: bool = Field(default=False)


class RetryConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    redis_url: str = Field(default="redis://localhost:6379/0")
    retry_enabled: bool = Field(default=True)
    retry_max_attempts: int = Field(default=3)
    retry_backoff_seconds: int = Field(default=10)
    retry_backoff_multiplier: int = Field(default=2)
    retry_job_ttl_seconds: int = Field(default=86400)


class PathConfig:
    def __init__(self) -> None:
        self.root: Path = Path(__file__).parent.parent
        self.data_raw: Path = self.root / "data" / "raw"
        self.data_processed: Path = self.root / "data" / "processed"
        self.data_debug: Path = self.root / "data" / "debug"
        self.logs: Path = self.root / "logs"


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _default_runpod_base_url() -> str | None:
    pod_id = os.getenv("RUNPOD_POD_ID")
    port = os.getenv("RUNPOD_PORT", "8000")
    if not pod_id:
        return None
    return f"https://{pod_id}-{port}.proxy.runpod.net/v1"


def _default_runpod_api_key() -> str | None:
    pod_id = os.getenv("RUNPOD_POD_ID")
    return _first_non_empty(
        os.getenv("RUNPOD_API_KEY"),
        f"sk-{pod_id}" if pod_id else None,
    )


db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
vector_config = VectorIndexConfig()
logging_config = LoggingConfig()
generation_config = GenerationConfig()
llm_config = LLMConfig()
routing_config = RoutingConfig()
retry_config = RetryConfig()
path_config = PathConfig()

# Compatibility shims for existing codepaths
DATABASE_URL = os.getenv("DATABASE_URL", db_config.connection_string)
MODEL_NAME = embed_config.embedding_model
RAG_DATA_DIR = os.getenv("RAG_DATA_DIR", str(path_config.data_raw))
CHUNK_SIZE = chunk_config.chunk_size
CHUNK_OVERLAP = chunk_config.chunk_overlap
HNSW_M = vector_config.hnsw_m
HNSW_EF_CONSTRUCTION = vector_config.hnsw_ef_construction
OLLAMA_BASE_URL = generation_config.ollama_base_url
OLLAMA_MODEL = generation_config.ollama_model
OLLAMA_MAX_TOKENS = generation_config.ollama_max_tokens
OLLAMA_TIMEOUT_SECONDS = generation_config.ollama_timeout_seconds
LLM_BASE_URL = llm_config.llm_base_url
LLM_MODEL = llm_config.llm_model
LLM_API_KEY = llm_config.llm_api_key
LLM_MAX_TOKENS = llm_config.llm_max_tokens
LLM_TEMPERATURE = llm_config.llm_temperature
LLM_TIMEOUT_SECONDS = llm_config.llm_timeout_seconds

LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", OLLAMA_BASE_URL)
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", OLLAMA_MODEL)
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "ollama")
LOCAL_LLM_MAX_TOKENS = int(
    os.getenv("LOCAL_LLM_MAX_TOKENS", str(OLLAMA_MAX_TOKENS)))
LOCAL_LLM_TIMEOUT_SECONDS = float(
    os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS))
)

CLOUD_LLM_BASE_URL = _first_non_empty(
    os.getenv("CLOUD_LLM_BASE_URL"),
    _default_runpod_base_url(),
    LLM_BASE_URL,
) or LLM_BASE_URL
CLOUD_LLM_MODEL = os.getenv("CLOUD_LLM_MODEL", LLM_MODEL)
CLOUD_LLM_API_KEY = _first_non_empty(
    os.getenv("CLOUD_LLM_API_KEY"),
    _default_runpod_api_key(),
    LLM_API_KEY,
) or LLM_API_KEY
CLOUD_LLM_MAX_TOKENS = int(
    os.getenv("CLOUD_LLM_MAX_TOKENS", str(LLM_MAX_TOKENS)))
CLOUD_LLM_TEMPERATURE = float(
    os.getenv("CLOUD_LLM_TEMPERATURE", str(LLM_TEMPERATURE)))
CLOUD_LLM_TIMEOUT_SECONDS = float(
    os.getenv("CLOUD_LLM_TIMEOUT_SECONDS", str(LLM_TIMEOUT_SECONDS))
)

LLM_ROUTE_THRESHOLD = routing_config.llm_route_threshold
ROUTE_REVISIONS_TO_CLOUD = routing_config.route_revisions_to_cloud
FORCE_CLOUD_LLM = routing_config.force_cloud_llm

REDIS_URL = retry_config.redis_url
RETRY_ENABLED = retry_config.retry_enabled
RETRY_MAX_ATTEMPTS = retry_config.retry_max_attempts
RETRY_BACKOFF_SECONDS = retry_config.retry_backoff_seconds
RETRY_BACKOFF_MULTIPLIER = retry_config.retry_backoff_multiplier
RETRY_JOB_TTL_SECONDS = retry_config.retry_job_ttl_seconds

GUIDELINE_SYNC_ENABLED = os.getenv("GUIDELINE_SYNC_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GUIDELINE_SYNC_INTERVAL_MINUTES = int(
    os.getenv("GUIDELINE_SYNC_INTERVAL_MINUTES", "10080")  # default: once per week
)
GUIDELINE_SYNC_RUN_ON_STARTUP = os.getenv(
    "GUIDELINE_SYNC_RUN_ON_STARTUP", "true"
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
GUIDELINE_SYNC_TIMEOUT_SECONDS = int(
    os.getenv("GUIDELINE_SYNC_TIMEOUT_SECONDS", "900")
)

import os
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

COMMON_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=PROJECT_ROOT / ".env",
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
)


class AppBaseSettings(BaseSettings):
    model_config = COMMON_SETTINGS_CONFIG


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


class LoggingConfig(AppBaseSettings):
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/rag.log")


class GenerationConfig(AppBaseSettings):
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="thewindmom/llama3-med42-8b")
    ollama_max_tokens: int = Field(default=1024)
    ollama_timeout_seconds: float = Field(default=60.0)


class LLMConfig(AppBaseSettings):
    llm_base_url: str = Field(default="http://localhost:11434/v1")
    llm_model: str = Field(default="thewindmom/llama3-med42-8b")
    llm_api_key: str = Field(default="ollama")
    llm_max_tokens: int = Field(default=1024)
    llm_temperature: float = Field(default=0.1)
    llm_timeout_seconds: float = Field(default=120.0)


class LocalLLMConfig(BaseModel):
    base_url: str
    model: str
    api_key: str
    max_tokens: int
    timeout_seconds: float


class CloudLLMConfig(BaseModel):
    base_url: str
    model: str
    api_key: str
    max_tokens: int
    temperature: float
    timeout_seconds: float


class RoutingConfig(AppBaseSettings):
    llm_route_threshold: float = Field(default=0.65)
    route_revisions_to_cloud: bool = Field(default=True)
    force_cloud_llm: bool = Field(default=False)


class RetryConfig(AppBaseSettings):
    redis_url: str = Field(default="redis://localhost:6379/0")
    retry_enabled: bool = Field(default=True)
    retry_max_attempts: int = Field(default=3)
    retry_backoff_seconds: int = Field(default=10)
    retry_backoff_multiplier: int = Field(default=2)
    retry_job_ttl_seconds: int = Field(default=86400)


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


def _build_local_llm_config(
    generation: GenerationConfig,
) -> LocalLLMConfig:
    return LocalLLMConfig(
        base_url=os.getenv("LOCAL_LLM_BASE_URL", generation.ollama_base_url),
        model=os.getenv("LOCAL_LLM_MODEL", generation.ollama_model),
        api_key=os.getenv("LOCAL_LLM_API_KEY", "ollama"),
        max_tokens=int(
            os.getenv("LOCAL_LLM_MAX_TOKENS", str(generation.ollama_max_tokens))
        ),
        timeout_seconds=float(
            os.getenv(
                "LOCAL_LLM_TIMEOUT_SECONDS",
                str(generation.ollama_timeout_seconds),
            )
        ),
    )


def _build_cloud_llm_config(llm: LLMConfig) -> CloudLLMConfig:
    fallback_base_url = (
        _first_non_empty(
            os.getenv("CLOUD_LLM_BASE_URL"),
            _default_runpod_base_url(),
            llm.llm_base_url,
        )
        or llm.llm_base_url
    )
    fallback_api_key = (
        _first_non_empty(
            os.getenv("CLOUD_LLM_API_KEY"),
            _default_runpod_api_key(),
            llm.llm_api_key,
        )
        or llm.llm_api_key
    )
    return CloudLLMConfig(
        base_url=fallback_base_url,
        model=os.getenv("CLOUD_LLM_MODEL", llm.llm_model),
        api_key=fallback_api_key,
        max_tokens=int(os.getenv("CLOUD_LLM_MAX_TOKENS", str(llm.llm_max_tokens))),
        temperature=float(
            os.getenv("CLOUD_LLM_TEMPERATURE", str(llm.llm_temperature))
        ),
        timeout_seconds=float(
            os.getenv("CLOUD_LLM_TIMEOUT_SECONDS", str(llm.llm_timeout_seconds))
        ),
    )


db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
vector_config = VectorIndexConfig()
logging_config = LoggingConfig()
generation_config = GenerationConfig()
llm_config = LLMConfig()
local_llm_config = _build_local_llm_config(generation_config)
cloud_llm_config = _build_cloud_llm_config(llm_config)
routing_config = RoutingConfig()
retry_config = RetryConfig()
path_config = PathConfig()

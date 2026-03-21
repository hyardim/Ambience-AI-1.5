from .base import COMMON_SETTINGS_CONFIG, PROJECT_ROOT, AppBaseSettings
from .llm import (
    CloudLLMConfig,
    GenerationConfig,
    LLMConfig,
    LocalLLMConfig,
    _default_runpod_api_key,
    _default_runpod_base_url,
    _first_non_empty,
    build_cloud_llm_config,
    build_local_llm_config,
)
from .runtime import (
    AlertingConfig,
    GuidelineSyncConfig,
    LoggingConfig,
    RetryConfig,
    RoutingConfig,
)
from .storage import (
    ChunkingConfig,
    DatabaseConfig,
    EmbeddingConfig,
    PathConfig,
    VectorIndexConfig,
)

db_config = DatabaseConfig()
embed_config = EmbeddingConfig()
chunk_config = ChunkingConfig()
vector_config = VectorIndexConfig()
logging_config = LoggingConfig()
generation_config = GenerationConfig()
llm_config = LLMConfig()
local_llm_config = build_local_llm_config(generation_config)
cloud_llm_config = build_cloud_llm_config(llm_config)
routing_config = RoutingConfig()
retry_config = RetryConfig()
alerting_config = AlertingConfig()
guideline_sync_config = GuidelineSyncConfig()
path_config = PathConfig()

# Backward-compatible module constants consumed by app startup code.
GUIDELINE_SYNC_ENABLED = guideline_sync_config.guideline_sync_enabled
GUIDELINE_SYNC_INTERVAL_MINUTES = guideline_sync_config.guideline_sync_interval_minutes
GUIDELINE_SYNC_RUN_ON_STARTUP = guideline_sync_config.guideline_sync_run_on_startup
GUIDELINE_SYNC_TIMEOUT_SECONDS = guideline_sync_config.guideline_sync_timeout_seconds

__all__ = [
    "COMMON_SETTINGS_CONFIG",
    "GUIDELINE_SYNC_ENABLED",
    "GUIDELINE_SYNC_INTERVAL_MINUTES",
    "GUIDELINE_SYNC_RUN_ON_STARTUP",
    "GUIDELINE_SYNC_TIMEOUT_SECONDS",
    "PROJECT_ROOT",
    "AlertingConfig",
    "AppBaseSettings",
    "ChunkingConfig",
    "CloudLLMConfig",
    "DatabaseConfig",
    "EmbeddingConfig",
    "GenerationConfig",
    "GuidelineSyncConfig",
    "LLMConfig",
    "LocalLLMConfig",
    "LoggingConfig",
    "PathConfig",
    "RetryConfig",
    "RoutingConfig",
    "VectorIndexConfig",
    "_default_runpod_api_key",
    "_default_runpod_base_url",
    "_first_non_empty",
    "alerting_config",
    "build_cloud_llm_config",
    "build_local_llm_config",
    "chunk_config",
    "cloud_llm_config",
    "db_config",
    "embed_config",
    "generation_config",
    "guideline_sync_config",
    "llm_config",
    "local_llm_config",
    "logging_config",
    "path_config",
    "retry_config",
    "routing_config",
    "vector_config",
]

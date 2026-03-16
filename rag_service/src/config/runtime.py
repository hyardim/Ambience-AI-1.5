from pydantic import Field

from .base import AppBaseSettings


class LoggingConfig(AppBaseSettings):
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/rag.log")


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

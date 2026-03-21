from pydantic import Field

from .base import AppBaseSettings


class LoggingConfig(AppBaseSettings):
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="logs/rag.log")


class RoutingConfig(AppBaseSettings):
    llm_route_threshold: float = Field(default=0.65)
    route_revisions_to_cloud: bool = Field(default=True)
    force_cloud_llm: bool = Field(default=False)
    medium_prompt_chars: int = Field(default=3500)
    long_prompt_chars: int = Field(default=7000)


class RetryConfig(AppBaseSettings):
    redis_url: str = Field(default="redis://localhost:6379/0")
    retry_enabled: bool = Field(default=True)
    retry_max_attempts: int = Field(default=3)
    retry_backoff_seconds: int = Field(default=10)
    retry_backoff_multiplier: int = Field(default=2)
    retry_max_backoff_seconds: int = Field(default=300)
    retry_job_ttl_seconds: int = Field(default=86400)
    retry_queue_job_timeout_seconds: int = Field(default=180)
    retry_queue_result_ttl_seconds: int = Field(default=60)
    retry_queue_failure_ttl_seconds: int = Field(default=86400)


class AlertingConfig(AppBaseSettings):
    llm_fallback_alert_webhook_url: str = Field(default="")
    llm_fallback_alert_timeout_seconds: float = Field(default=2.0)


class GuidelineSyncConfig(AppBaseSettings):
    guideline_sync_enabled: bool = Field(default=False)
    guideline_sync_interval_minutes: int = Field(default=10080)
    guideline_sync_run_on_startup: bool = Field(default=True)
    guideline_sync_timeout_seconds: int = Field(default=900)

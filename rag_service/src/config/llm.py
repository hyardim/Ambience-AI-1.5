import os
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .base import AppBaseSettings


class GenerationConfig(AppBaseSettings):
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="thewindmom/llama3-med42-8b")
    ollama_max_tokens: int = Field(default=1024)
    ollama_timeout_seconds: float = Field(default=60.0)
    prompt_variant: str = Field(default="new")


class LLMConfig(AppBaseSettings):
    llm_base_url: str = Field(default="http://localhost:11434/v1")
    llm_model: str = Field(default="m42-health/Llama3-Med42-70B")
    llm_api_key: str = Field(default="ollama")
    llm_max_tokens: int = Field(default=1024)
    llm_temperature: float = Field(default=0.1)
    llm_timeout_seconds: float = Field(default=120.0)


class LocalLLMConfig(BaseModel):
    base_url: str
    model: str
    api_key: str
    max_tokens: int
    temperature: float
    timeout_seconds: float


class CloudLLMConfig(BaseModel):
    base_url: str
    model: str
    api_key: str
    max_tokens: int
    temperature: float
    timeout_seconds: float


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


def _running_in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolve_local_base_url(generation: GenerationConfig) -> str:
    explicit_local_base = os.getenv("LOCAL_LLM_BASE_URL")
    if explicit_local_base:
        return explicit_local_base
    if _running_in_docker():
        docker_override = os.getenv("DOCKER_OLLAMA_BASE_URL")
        if docker_override:
            return docker_override
    return generation.ollama_base_url


def build_local_llm_config(generation: GenerationConfig) -> LocalLLMConfig:
    return LocalLLMConfig(
        base_url=_resolve_local_base_url(generation),
        model=os.getenv("LOCAL_LLM_MODEL", generation.ollama_model),
        api_key=os.getenv("LOCAL_LLM_API_KEY", "ollama"),
        max_tokens=int(
            os.getenv("LOCAL_LLM_MAX_TOKENS", str(generation.ollama_max_tokens))
        ),
        temperature=float(
            os.getenv("LOCAL_LLM_TEMPERATURE", str(LLMConfig().llm_temperature))
        ),
        timeout_seconds=float(
            os.getenv(
                "LOCAL_LLM_TIMEOUT_SECONDS",
                str(generation.ollama_timeout_seconds),
            )
        ),
    )


def build_cloud_llm_config(llm: LLMConfig) -> CloudLLMConfig:
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
        temperature=float(os.getenv("CLOUD_LLM_TEMPERATURE", str(llm.llm_temperature))),
        timeout_seconds=float(
            os.getenv("CLOUD_LLM_TIMEOUT_SECONDS", str(llm.llm_timeout_seconds))
        ),
    )


def cloud_llm_is_configured(config: CloudLLMConfig) -> bool:
    """Return True only when the cloud provider looks intentionally configured.

    Local Docker/dev environments often carry placeholder values so the config
    object can be constructed. Routing should not treat those placeholders as a
    usable remote provider.
    """

    base_url = config.base_url.strip()
    api_key = config.api_key.strip()
    model = config.model.strip()
    if not base_url or not api_key or not model:
        return False

    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").strip().lower()
    if not parsed.scheme or not hostname:
        return False

    placeholder_hosts = {"example.invalid", "localhost", "127.0.0.1"}
    if hostname in placeholder_hosts and "runpod.net" not in hostname:
        return False

    placeholder_tokens = {
        "dummy",
        "placeholder",
        "changeme",
        "replace-me",
        "replace_with_real_key",
        "required",
    }
    normalized_key = api_key.lower()
    return not (
        normalized_key in placeholder_tokens
        or normalized_key.startswith("required_")
    )

from typing import Any, Literal, cast

import httpx

from ..config import (
    alerting_config,
    cloud_llm_config,
    local_llm_config,
    path_config,
)
from ..utils.logger import setup_logger
from ..utils.telemetry import append_jsonl

ProviderName = Literal["local", "cloud"]
logger = setup_logger(__name__)
PROVIDER_ALERTS_PATH = path_config.logs / "provider_alerts.jsonl"


class ProviderRequestError(RuntimeError):
    """Provider-specific generation failure with retry metadata."""

    def __init__(
        self,
        message: str,
        *,
        provider: ProviderName,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code


class ModelGenerationError(RuntimeError):
    """Raised when both primary and fallback model providers fail."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def _fallback_provider(provider: ProviderName) -> ProviderName:
    return "cloud" if provider == "local" else "local"


def _emit_provider_alert(
    *,
    event: str,
    primary_provider: ProviderName,
    fallback_provider: ProviderName | None,
    detail: str,
) -> None:
    payload = {
        "event": event,
        "primary_provider": primary_provider,
        "fallback_provider": fallback_provider,
        "detail": detail,
    }
    append_jsonl(PROVIDER_ALERTS_PATH, payload)
    _send_provider_alert_webhook(payload)


def _send_provider_alert_webhook(payload: dict[str, Any]) -> None:
    webhook_url = alerting_config.llm_fallback_alert_webhook_url.strip()
    if not webhook_url:
        return

    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            timeout=alerting_config.llm_fallback_alert_timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Provider alert webhook delivery failed: %s", exc)


async def warmup_model(provider: ProviderName = "local") -> None:
    """Warm up the local model when applicable.

    Cloud models are managed remotely, so warmup is a no-op for the cloud path.
    """
    if provider != "local":
        logger.info(
            "Cloud model warmup skipped; remote endpoint manages model lifecycle."
        )
        return

    payload = {
        "model": local_llm_config.model,
        "prompt": "warmup",
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(
            timeout=local_llm_config.timeout_seconds
        ) as client:
            resp = await client.post(
                f"{local_llm_config.base_url.rstrip('/')}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
        logger.info(
            "Local model '%s' warmed up and kept alive.",
            local_llm_config.model,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "Local model warmup failed (model may still be loading): %s", exc
        )


async def _generate_local_answer(prompt: str, max_tokens: int | None = None) -> str:
    payload = {
        "model": local_llm_config.model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": max_tokens or local_llm_config.max_tokens},
    }

    try:
        async with httpx.AsyncClient(
            timeout=local_llm_config.timeout_seconds
        ) as client:
            resp = await client.post(
                f"{local_llm_config.base_url.rstrip('/')}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            return str(data.get("response", "")).strip()
    except httpx.TimeoutException as exc:
        raise ProviderRequestError(
            f"Local model request timed out: {exc}",
            provider="local",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ProviderRequestError(
            f"Local model connection failed: {exc}",
            provider="local",
            retryable=True,
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        raise ProviderRequestError(
            f"Local model returned HTTP {status_code}",
            provider="local",
            retryable=status_code >= 500,
            status_code=status_code,
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderRequestError(
            f"Local model request failed: {exc}",
            provider="local",
            retryable=True,
        ) from exc


async def _generate_cloud_answer(prompt: str, max_tokens: int | None = None) -> str:
    return await request_chat_completion(
        provider="cloud",
        base_url=cloud_llm_config.base_url,
        api_key=cloud_llm_config.api_key,
        model=cloud_llm_config.model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens or cloud_llm_config.max_tokens,
        temperature=cloud_llm_config.temperature,
        timeout_seconds=cloud_llm_config.timeout_seconds,
    )


def _extract_chat_completion_text(data: dict[str, Any]) -> str:
    choices = cast(list[dict[str, Any]], data.get("choices", []))
    if not choices:
        return ""
    return str(
        cast(dict[str, Any], choices[0]).get("message", {}).get("content", "")
    ).strip()


def _auth_headers(api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _wrap_provider_request_error(
    exc: httpx.HTTPError,
    *,
    provider: ProviderName,
) -> ProviderRequestError:
    provider_name = "Cloud" if provider == "cloud" else "Local"
    if isinstance(exc, httpx.TimeoutException):
        return ProviderRequestError(
            f"{provider_name} model request timed out: {exc}",
            provider=provider,
            retryable=True,
        )
    if isinstance(exc, httpx.ConnectError):
        return ProviderRequestError(
            f"{provider_name} model connection failed: {exc}",
            provider=provider,
            retryable=True,
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return ProviderRequestError(
            f"{provider_name} model returned HTTP {status_code}",
            provider=provider,
            retryable=status_code >= 500,
            status_code=status_code,
        )
    return ProviderRequestError(
        f"{provider_name} model request failed: {exc}",
        provider=provider,
        retryable=True,
    )


def _request_chat_completion_sync(
    *,
    provider: ProviderName,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    timeout_seconds: float,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=_auth_headers(api_key),
            )
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            return _extract_chat_completion_text(data)
    except httpx.HTTPError as exc:
        raise _wrap_provider_request_error(exc, provider=provider) from exc


async def request_chat_completion(
    *,
    provider: ProviderName,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    timeout_seconds: float,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=_auth_headers(api_key),
            )
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            return _extract_chat_completion_text(data)
    except httpx.HTTPError as exc:
        raise _wrap_provider_request_error(exc, provider=provider) from exc


async def _call_local_model(prompt: str, max_tokens: int | None = None) -> str:
    return await _generate_local_answer(prompt, max_tokens=max_tokens)


async def _call_cloud_model(prompt: str, max_tokens: int | None = None) -> str:
    return await _generate_cloud_answer(prompt, max_tokens=max_tokens)


async def generate_answer(
    prompt: str,
    max_tokens: int | None = None,
    provider: ProviderName = "local",
) -> str:
    """Generate an answer using the selected provider with fallback."""
    attempts: list[str] = []
    attempt_errors: list[ProviderRequestError] = []

    for index, current_provider in enumerate(
        (provider, _fallback_provider(provider)),
        start=1,
    ):
        try:
            if current_provider == "cloud":
                response = await _call_cloud_model(prompt, max_tokens=max_tokens)
            else:
                response = await _call_local_model(prompt, max_tokens=max_tokens)

            if not response.strip():
                raise ProviderRequestError(
                    f"{current_provider.capitalize()} model returned an empty response",
                    provider=current_provider,
                    retryable=True,
                )

            if index > 1:
                logger.info(
                    "Generation fallback succeeded with provider=%s",
                    current_provider,
                )
                _emit_provider_alert(
                    event="provider_fallback_succeeded",
                    primary_provider=provider,
                    fallback_provider=current_provider,
                    detail=(
                        "Primary provider failed and fallback provider returned a "
                        "response"
                    ),
                )

            return response
        except Exception as exc:
            attempts.append(f"{current_provider}: {exc}")
            if isinstance(exc, ProviderRequestError):
                attempt_errors.append(exc)
            if index == 1:
                fallback_provider = _fallback_provider(current_provider)
                logger.warning(
                    "Primary generation provider failed (provider=%s): %s. "
                    "Trying fallback provider=%s.",
                    current_provider,
                    exc,
                    fallback_provider,
                )
                _emit_provider_alert(
                    event="provider_fallback_attempt",
                    primary_provider=current_provider,
                    fallback_provider=fallback_provider,
                    detail=str(exc),
                )

    retryable = len(attempt_errors) == len(attempts) and all(
        error.retryable for error in attempt_errors
    )
    _emit_provider_alert(
        event="provider_all_failed",
        primary_provider=provider,
        fallback_provider=_fallback_provider(provider),
        detail=" | ".join(attempts),
    )
    raise ModelGenerationError(
        "All model providers failed. " + " | ".join(attempts),
        retryable=retryable,
    )

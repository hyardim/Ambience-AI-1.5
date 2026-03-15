from typing import Any, Literal, cast

import httpx

from ..config import (
    CLOUD_LLM_API_KEY,
    CLOUD_LLM_BASE_URL,
    CLOUD_LLM_MAX_TOKENS,
    CLOUD_LLM_MODEL,
    CLOUD_LLM_TEMPERATURE,
    CLOUD_LLM_TIMEOUT_SECONDS,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_MAX_TOKENS,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_TIMEOUT_SECONDS,
)

ProviderName = Literal["local", "cloud"]


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


async def warmup_model(provider: ProviderName = "local") -> None:
    """Warm up the local model when applicable.

    Cloud models are managed remotely, so warmup is a no-op for the cloud path.
    """
    if provider != "local":
        print("ℹ️ Cloud model warmup skipped; remote endpoint manages model lifecycle.")
        return

    payload = {
        "model": LOCAL_LLM_MODEL,
        "prompt": "warmup",
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{LOCAL_LLM_BASE_URL.rstrip('/')}/api/generate", json=payload
            )
            resp.raise_for_status()
        print(f"✅ Local model '{LOCAL_LLM_MODEL}' warmed up and kept alive.")
    except Exception as exc:  # pragma: no cover
        print(f"⚠️  Local model warmup failed (model may still be loading): {exc}")


async def _generate_local_answer(prompt: str, max_tokens: int | None = None) -> str:
    payload = {
        "model": LOCAL_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": max_tokens or LOCAL_LLM_MAX_TOKENS},
    }

    try:
        async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{LOCAL_LLM_BASE_URL.rstrip('/')}/api/generate", json=payload
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
    payload = {
        "model": CLOUD_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens or CLOUD_LLM_MAX_TOKENS,
        "temperature": CLOUD_LLM_TEMPERATURE,
        "stream": False,
    }

    headers: dict[str, str] = {}
    if CLOUD_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {CLOUD_LLM_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=CLOUD_LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{CLOUD_LLM_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
            return str(
                cast(
                    dict[str, Any],
                    cast(list[dict[str, Any]], data.get("choices", [{}]))[0],
                )
                .get("message", {})
                .get("content", "")
            ).strip()
    except httpx.TimeoutException as exc:
        raise ProviderRequestError(
            f"Cloud model request timed out: {exc}",
            provider="cloud",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ProviderRequestError(
            f"Cloud model connection failed: {exc}",
            provider="cloud",
            retryable=True,
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        raise ProviderRequestError(
            f"Cloud model returned HTTP {status_code}",
            provider="cloud",
            retryable=status_code >= 500,
            status_code=status_code,
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderRequestError(
            f"Cloud model request failed: {exc}",
            provider="cloud",
            retryable=True,
        ) from exc


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
                raise RuntimeError(
                    f"{current_provider.capitalize()} model returned an empty response"
                )

            if index > 1:
                print(
                    f"🔁 Generation fallback succeeded with provider={current_provider}"
                )

            return response
        except Exception as exc:
            attempts.append(f"{current_provider}: {exc}")
            if isinstance(exc, ProviderRequestError):
                attempt_errors.append(exc)
            if index == 1:
                print(
                    "⚠️ Primary generation provider failed "
                    f"(provider={current_provider}): {exc}. "
                    f"Trying fallback provider={_fallback_provider(current_provider)}."
                )

    retryable = len(attempt_errors) == len(attempts) and all(
        error.retryable for error in attempt_errors
    )
    raise ModelGenerationError(
        "All model providers failed. " + " | ".join(attempts),
        retryable=retryable,
    )

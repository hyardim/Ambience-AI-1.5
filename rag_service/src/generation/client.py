import httpx
from typing import Literal

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


class ModelGenerationError(RuntimeError):
    """Raised when both primary and fallback model providers fail."""


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
        "keep_alive": -1,  # keep loaded indefinitely
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{LOCAL_LLM_BASE_URL}/api/generate", json=payload
            )
            resp.raise_for_status()
        print(f"✅ Local model '{LOCAL_LLM_MODEL}' warmed up and kept alive.")
    except Exception as exc:  # pragma: no cover
        print(
            f"⚠️  Local model warmup failed (model may still be loading): {exc}")


async def generate_answer(
    prompt: str,
    max_tokens: int | None = None,
    provider: ProviderName = "local",
) -> str:
    """Generate an answer using the selected provider with fallback.

    If the primary provider fails, automatically retry once with the other
    provider. If both fail, raise a single aggregated error.
    """
    attempts: list[str] = []

    for index, current_provider in enumerate(
        (provider, _fallback_provider(provider)),
        start=1,
    ):
        try:
            if current_provider == "cloud":
                response = await _generate_cloud_answer(
                    prompt,
                    max_tokens=max_tokens,
                )
            else:
                response = await _generate_local_answer(
                    prompt,
                    max_tokens=max_tokens,
                )

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
            if index == 1:
                print(
                    f"⚠️ Primary generation provider failed (provider={current_provider}): {exc}. "
                    f"Trying fallback provider={_fallback_provider(current_provider)}."
                )

    raise ModelGenerationError(
        "All model providers failed. " + " | ".join(attempts)
    )


async def _generate_local_answer(prompt: str, max_tokens: int | None = None) -> str:
    """Call the local Ollama server to generate a response."""
    payload = {
        "model": LOCAL_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,  # prevent idle unload between requests
        "options": {"num_predict": max_tokens or LOCAL_LLM_MAX_TOKENS},
    }

    try:
        async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{LOCAL_LLM_BASE_URL}/api/generate", json=payload
            )
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns the final text in the "response" field for
            # non-streaming requests
            return data.get("response", "").strip()
    except httpx.HTTPError as exc:  # pragma: no cover - passthrough for FastAPI handler
        raise RuntimeError(f"Local model request failed: {exc}") from exc


async def _generate_cloud_answer(prompt: str, max_tokens: int | None = None) -> str:
    """Call the cloud RunPod endpoint using an OpenAI-compatible API."""
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
            data = resp.json()
            return (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
    except httpx.HTTPError as exc:  # pragma: no cover - passthrough for FastAPI handler
        raise RuntimeError(f"Cloud model request failed: {exc}") from exc

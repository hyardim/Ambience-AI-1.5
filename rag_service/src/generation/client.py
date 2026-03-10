from typing import Literal

import httpx

from ..config import (
    CLOUD_LLM_API_KEY,
    CLOUD_LLM_BASE_URL,
    CLOUD_LLM_MODEL,
    CLOUD_LLM_TIMEOUT_SECONDS,
    LOCAL_LLM_API_KEY,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_MODEL,
    LOCAL_LLM_TIMEOUT_SECONDS,
    OLLAMA_MAX_TOKENS,
    OLLAMA_MODEL,
)

ProviderName = Literal["local", "cloud"]

async def _call_local_model(prompt: str, max_tokens: int | None = None) -> str:
    payload = {
        "model": LOCAL_LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": max_tokens or OLLAMA_MAX_TOKENS},
    }

    headers: dict[str, str] = {}
    if LOCAL_LLM_API_KEY and LOCAL_LLM_API_KEY != "ollama":
        headers["Authorization"] = f"Bearer {LOCAL_LLM_API_KEY}"

    async with httpx.AsyncClient(timeout=LOCAL_LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{LOCAL_LLM_BASE_URL.rstrip('/')}/api/generate",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()


async def _call_cloud_model(prompt: str, max_tokens: int | None = None) -> str:
    payload = {
        "model": CLOUD_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens or OLLAMA_MAX_TOKENS,
        "temperature": 0.1,
        "stream": False,
    }

    headers: dict[str, str] = {}
    if CLOUD_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {CLOUD_LLM_API_KEY}"

    async with httpx.AsyncClient(timeout=CLOUD_LLM_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{CLOUD_LLM_BASE_URL.rstrip('/')}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


async def warmup_model() -> None:
    """Send a minimal prompt to Ollama so the model is loaded into memory.

    Ollama unloads idle models after a configurable timeout (default 5 min).
    Calling this on service startup avoids a cold-load failure on the first
    real request.  The keep_alive value in every payload also prevents the
    model from being unloaded again between requests.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": "warmup",
        "stream": False,
        "keep_alive": -1,  # keep loaded indefinitely
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{LOCAL_LLM_BASE_URL.rstrip('/')}/api/generate", json=payload
            )
            resp.raise_for_status()
        print(f"✅ Local model '{OLLAMA_MODEL}' warmed up and kept alive.")
    except Exception as exc:  # pragma: no cover
        print(f"⚠️  Local model warmup failed (model may still be loading): {exc}")


async def generate_answer(
    prompt: str,
    *,
    max_tokens: int | None = None,
    provider: ProviderName = "local",
) -> str:
    """Call preferred provider first, then fallback to the other provider."""
    first = provider
    second: ProviderName = "cloud" if provider == "local" else "local"

    first_error: Exception | None = None

    try:
        if first == "cloud":
            return await _call_cloud_model(prompt, max_tokens=max_tokens)
        return await _call_local_model(prompt, max_tokens=max_tokens)
    except Exception as exc:
        first_error = exc

    try:
        if second == "cloud":
            return await _call_cloud_model(prompt, max_tokens=max_tokens)
        return await _call_local_model(prompt, max_tokens=max_tokens)
    except Exception as second_error:
        raise RuntimeError(
            f"Both model endpoints failed. First={first} error={first_error}; "
            f"Fallback={second} error={second_error}"
        ) from second_error

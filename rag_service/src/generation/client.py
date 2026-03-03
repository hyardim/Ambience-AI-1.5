import httpx

from ..config import OLLAMA_BASE_URL, OLLAMA_MAX_TOKENS, OLLAMA_MODEL


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
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
        print(f"✅ Ollama model '{OLLAMA_MODEL}' warmed up and kept alive.")
    except Exception as exc:  # pragma: no cover
        print(f"⚠️  Ollama warmup failed (model may still be loading): {exc}")


async def generate_answer(prompt: str, max_tokens: int | None = None) -> str:
    """Call the local Ollama server to generate a response."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": -1,  # prevent idle unload between requests
        "options": {"num_predict": max_tokens or OLLAMA_MAX_TOKENS},
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Ollama returns the final text in the "response" field for
            # non-streaming requests
            return data.get("response", "").strip()
    except httpx.HTTPError as exc:  # pragma: no cover - passthrough for FastAPI handler
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

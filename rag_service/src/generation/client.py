import httpx

from ..config import OLLAMA_BASE_URL, OLLAMA_MAX_TOKENS, OLLAMA_MODEL


async def generate_answer(prompt: str, max_tokens: int | None = None) -> str:
    """Call the local Ollama server to generate a response."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
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

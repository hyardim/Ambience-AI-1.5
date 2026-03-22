import pytest
import httpx

from src.generation import client
from src.generation.client import ModelGenerationError, ProviderRequestError


class _DummyResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", "http://test")
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError("status", request=req, response=resp)

    def json(self):
        return self._payload


class _DummyAsyncClient:
    def __init__(self, *args, responder=None, **kwargs):
        self._responder = responder

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, *args, **kwargs):
        if self._responder is None:
            return _DummyResponse()
        return self._responder(*args, **kwargs)


@pytest.mark.asyncio
async def test_generate_answer_routes_local_first_and_falls_back_to_cloud(monkeypatch):
    calls: list[str] = []

    async def fail_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        calls.append("local")
        raise RuntimeError("local down")

    async def ok_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        calls.append("cloud")
        return "cloud answer"

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", ok_cloud)

    answer = await client.generate_answer(
        "prompt",
        max_tokens=64,
        provider="local",
    )

    assert answer == "cloud answer"
    assert calls == ["local", "cloud"]


@pytest.mark.asyncio
async def test_generate_answer_routes_cloud_first_and_falls_back_to_local(monkeypatch):
    calls: list[str] = []

    async def fail_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        calls.append("cloud")
        raise RuntimeError("cloud down")

    async def ok_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        calls.append("local")
        return "local answer"

    monkeypatch.setattr(client, "_call_local_model", ok_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    answer = await client.generate_answer(
        "prompt",
        max_tokens=64,
        provider="cloud",
    )

    assert answer == "local answer"
    assert calls == ["cloud", "local"]


@pytest.mark.asyncio
async def test_generate_answer_cloud_first_success(monkeypatch):
    calls: list[str] = []

    async def ok_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        calls.append("cloud")
        return "cloud answer"

    async def ok_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        calls.append("local")
        return "local answer"

    monkeypatch.setattr(client, "_call_local_model", ok_local)
    monkeypatch.setattr(client, "_call_cloud_model", ok_cloud)

    answer = await client.generate_answer(
        "prompt",
        max_tokens=64,
        provider="cloud",
    )

    assert answer == "cloud answer"
    assert calls == ["cloud"]


@pytest.mark.asyncio
async def test_generate_answer_raises_when_both_fail(monkeypatch):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise RuntimeError("cloud down")

    async def fail_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise RuntimeError("local down")

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(ModelGenerationError, match="All model providers failed"):
        await client.generate_answer(
            "prompt",
            max_tokens=64,
            provider="cloud",
        )


@pytest.mark.asyncio
async def test_generate_answer_sets_retryable_when_all_provider_errors_retryable(
    monkeypatch,
):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise ProviderRequestError(
            "cloud timeout", provider="cloud", retryable=True
        )

    async def fail_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise ProviderRequestError(
            "local connect", provider="local", retryable=True
        )

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(ModelGenerationError) as exc_info:
        await client.generate_answer("prompt", provider="cloud")

    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_generate_answer_sets_retryable_false_for_non_retryable_provider_error(
    monkeypatch,
):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise ProviderRequestError(
            "cloud 400", provider="cloud", retryable=False, status_code=400
        )

    async def fail_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise ProviderRequestError(
            "local timeout", provider="local", retryable=True
        )

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(ModelGenerationError) as exc_info:
        await client.generate_answer("prompt", provider="cloud")

    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_generate_answer_sets_retryable_false_for_non_provider_error(monkeypatch):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise RuntimeError("cloud panic")

    async def fail_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise ProviderRequestError(
            "local timeout", provider="local", retryable=True
        )

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(ModelGenerationError) as exc_info:
        await client.generate_answer("prompt", provider="cloud")

    assert exc_info.value.retryable is False


def test_fallback_provider_switches_between_local_and_cloud() -> None:
    assert client._fallback_provider("local") == "cloud"
    assert client._fallback_provider("cloud") == "local"


@pytest.mark.asyncio
async def test_warmup_model_cloud_provider_is_noop(monkeypatch):
    post_called = {"value": False}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            post_called["value"] = True
            raise AssertionError("post should not be called for cloud warmup")

    monkeypatch.setattr(client.httpx, "AsyncClient", DummyClient)

    await client.warmup_model(provider="cloud")
    assert post_called["value"] is False


@pytest.mark.asyncio
async def test_warmup_model_local_posts_to_generate(monkeypatch):
    called = {"url": "", "json": None}

    class DummyResponse:
        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json=None):
            called["url"] = url
            called["json"] = json
            return DummyResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", DummyClient)

    await client.warmup_model(provider="local")

    assert called["url"].endswith("/api/generate")
    assert called["json"]["prompt"] == "warmup"


@pytest.mark.asyncio
async def test_generate_local_answer_success(monkeypatch):
    def responder(*args, **kwargs):
        return _DummyResponse(payload={"response": "  local ok  "})

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(responder=responder),
    )

    answer = await client._generate_local_answer("prompt")
    assert answer == "local ok"


@pytest.mark.asyncio
async def test_generate_cloud_answer_success(monkeypatch):
    def responder(*args, **kwargs):
        return _DummyResponse(
            payload={"choices": [{"message": {"content": "  cloud ok "}}]}
        )

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(responder=responder),
    )

    answer = await client._generate_cloud_answer("prompt")
    assert answer == "cloud ok"


@pytest.mark.asyncio
async def test_generate_local_answer_timeout_maps_to_retryable_provider_error(
    monkeypatch,
):
    def responder(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(responder=responder),
    )

    with pytest.raises(ProviderRequestError) as exc_info:
        await client._generate_local_answer("prompt")

    assert exc_info.value.provider == "local"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_generate_cloud_answer_connect_error_maps_to_retryable_provider_error(
    monkeypatch,
):
    def responder(*args, **kwargs):
        raise httpx.ConnectError("connect", request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(responder=responder),
    )

    with pytest.raises(ProviderRequestError) as exc_info:
        await client._generate_cloud_answer("prompt")

    assert exc_info.value.provider == "cloud"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_generate_cloud_answer_http_400_maps_to_non_retryable_provider_error(
    monkeypatch,
):
    def responder(*args, **kwargs):
        return _DummyResponse(status_code=400)

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(responder=responder),
    )

    with pytest.raises(ProviderRequestError) as exc_info:
        await client._generate_cloud_answer("prompt")

    assert exc_info.value.provider == "cloud"
    assert exc_info.value.retryable is False
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_generate_local_answer_http_500_maps_to_retryable_provider_error(
    monkeypatch,
):
    def responder(*args, **kwargs):
        return _DummyResponse(status_code=500)

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(responder=responder),
    )

    with pytest.raises(ProviderRequestError) as exc_info:
        await client._generate_local_answer("prompt")

    assert exc_info.value.provider == "local"
    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 500

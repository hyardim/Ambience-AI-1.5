import pytest

from src.generation import client


@pytest.mark.anyio
async def test_generate_answer_routes_local_first_and_falls_back_to_cloud(monkeypatch):
    calls: list[str] = []

    async def fail_local(prompt: str, max_tokens=None) -> str:
        calls.append("local")
        raise RuntimeError("local down")

    async def ok_cloud(prompt: str, max_tokens=None) -> str:
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


@pytest.mark.anyio
async def test_generate_answer_routes_cloud_first_and_falls_back_to_local(monkeypatch):
    calls: list[str] = []

    async def fail_cloud(prompt: str, max_tokens=None) -> str:
        calls.append("cloud")
        raise RuntimeError("cloud down")

    async def ok_local(prompt: str, max_tokens=None) -> str:
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


@pytest.mark.anyio
async def test_generate_answer_cloud_first_success(monkeypatch):
    calls: list[str] = []

    async def ok_cloud(prompt: str, max_tokens=None) -> str:
        calls.append("cloud")
        return "cloud answer"

    async def ok_local(prompt: str, max_tokens=None) -> str:
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


@pytest.mark.anyio
async def test_generate_answer_raises_when_both_fail(monkeypatch):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:
        raise RuntimeError("cloud down")

    async def fail_local(prompt: str, max_tokens=None) -> str:
        raise RuntimeError("local down")

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(
        client.ModelGenerationError,
        match="All model providers failed",
    ) as exc_info:
        await client.generate_answer(
            "prompt",
            max_tokens=64,
            provider="cloud",
        )
    assert exc_info.value.retryable is False


@pytest.mark.anyio
async def test_generate_answer_sets_retryable_when_all_provider_errors_retryable(
    monkeypatch,
):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:
        raise client.ProviderRequestError(
            "cloud timeout",
            provider="cloud",
            retryable=True,
        )

    async def fail_local(prompt: str, max_tokens=None) -> str:
        raise client.ProviderRequestError(
            "local connect",
            provider="local",
            retryable=True,
        )

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(client.ModelGenerationError) as exc_info:
        await client.generate_answer("prompt", provider="cloud")

    assert exc_info.value.retryable is True


@pytest.mark.anyio
async def test_generate_answer_sets_retryable_false_for_non_retryable_provider_error(
    monkeypatch,
):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:
        raise client.ProviderRequestError(
            "cloud bad request",
            provider="cloud",
            retryable=False,
            status_code=400,
        )

    async def fail_local(prompt: str, max_tokens=None) -> str:
        raise client.ProviderRequestError(
            "local timeout",
            provider="local",
            retryable=True,
        )

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(client.ModelGenerationError) as exc_info:
        await client.generate_answer("prompt", provider="cloud")

    assert exc_info.value.retryable is False


@pytest.mark.anyio
async def test_generate_answer_sets_retryable_false_for_non_provider_error(monkeypatch):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:
        raise RuntimeError("cloud panic")

    async def fail_local(prompt: str, max_tokens=None) -> str:
        raise client.ProviderRequestError(
            "local timeout",
            provider="local",
            retryable=True,
        )

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(client.ModelGenerationError) as exc_info:
        await client.generate_answer("prompt", provider="cloud")

    assert exc_info.value.retryable is False


def test_fallback_provider_switches_between_local_and_cloud() -> None:
    assert client._fallback_provider("local") == "cloud"
    assert client._fallback_provider("cloud") == "local"


@pytest.mark.anyio
async def test_warmup_model_skips_cloud(monkeypatch):
    messages: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(
        client.logger,
        "info",
        lambda message, *args: messages.append((message, args)),
    )

    await client.warmup_model("cloud")

    assert "Cloud model warmup skipped" in messages[0][0]


@pytest.mark.anyio
async def test_warmup_model_logs_success(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            return FakeResponse()

    messages: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())
    monkeypatch.setattr(
        client.logger,
        "info",
        lambda message, *args: messages.append((message, args)),
    )

    await client.warmup_model("local")

    assert any("warmed up and kept alive" in message for message, _ in messages)


@pytest.mark.anyio
async def test_warmup_model_local_posts_to_generate(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())
    monkeypatch.setattr(client.local_llm_config, "base_url", "http://localhost:11434")
    monkeypatch.setattr(client.local_llm_config, "model", "demo-model")

    await client.warmup_model("local")

    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"] == {
        "model": "demo-model",
        "prompt": "warmup",
        "stream": False,
        "keep_alive": -1,
        "options": {"num_predict": 1},
    }


@pytest.mark.anyio
async def test_warmup_model_logs_failure(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            raise RuntimeError("boom")

    messages: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())
    monkeypatch.setattr(
        client.logger,
        "warning",
        lambda message, *args: messages.append((message, args)),
    )

    await client.warmup_model("local")

    assert any("warmup failed" in message for message, _ in messages)


@pytest.mark.anyio
async def test_generate_local_answer_maps_http_status(monkeypatch):
    request = client.httpx.Request("POST", "http://local")
    response = client.httpx.Response(503, request=request)

    class FakeResponse:
        def raise_for_status(self) -> None:
            raise client.httpx.HTTPStatusError(
                "bad", request=request, response=response
            )

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_local_answer("prompt")

    assert exc_info.value.provider == "local"
    assert exc_info.value.retryable is True
    assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_generate_local_answer_maps_timeout(monkeypatch):
    request = client.httpx.Request("POST", "http://local")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            raise client.httpx.TimeoutException("slow", request=request)

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_local_answer("prompt")

    assert exc_info.value.provider == "local"


@pytest.mark.anyio
async def test_generate_local_answer_success(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"response": " local answer "}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    assert await client._generate_local_answer("prompt") == "local answer"


@pytest.mark.anyio
async def test_generate_local_answer_maps_connect_error(monkeypatch):
    request = client.httpx.Request("POST", "http://local")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            raise client.httpx.ConnectError("down", request=request)

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_local_answer("prompt")

    assert exc_info.value.provider == "local"


def test_request_chat_completion_sync_returns_text(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": " cloud answer "}}]}

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(
            self,
            url: str,
            *,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "Client", FakeClient)

    answer = client._request_chat_completion_sync(
        provider="cloud",
        base_url="https://api.example.com/v1",
        api_key="secret",
        model="gpt-test",
        messages=[{"role": "user", "content": "prompt"}],
        max_tokens=50,
        temperature=0.2,
        timeout_seconds=33.0,
    )

    assert answer == "cloud answer"
    assert captured["timeout"] == 33.0
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer secret"}


def test_request_chat_completion_sync_wraps_http_errors(monkeypatch) -> None:
    request = client.httpx.Request("POST", "https://api.example.com")
    response = client.httpx.Response(502, request=request)

    class FakeClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(
            self,
            url: str,
            *,
            json: dict[str, object],
            headers: dict[str, str],
        ) -> object:
            raise client.httpx.HTTPStatusError(
                "bad",
                request=request,
                response=response,
            )

    monkeypatch.setattr(client.httpx, "Client", FakeClient)

    with pytest.raises(client.ProviderRequestError) as exc_info:
        client._request_chat_completion_sync(
            provider="cloud",
            base_url="https://api.example.com/v1",
            api_key="secret",
            model="gpt-test",
            messages=[{"role": "user", "content": "prompt"}],
            max_tokens=50,
            temperature=0.2,
            timeout_seconds=33.0,
        )

    assert exc_info.value.provider == "cloud"
    assert exc_info.value.status_code == 502


def test_send_provider_alert_webhook_skips_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(client.alerting_config, "llm_fallback_alert_webhook_url", "")

    called = {"value": False}

    def fake_post(*args, **kwargs):
        called["value"] = True
        return object()

    monkeypatch.setattr(client.httpx, "post", fake_post)

    client._send_provider_alert_webhook({"event": "provider_fallback_attempt"})

    assert called["value"] is False


def test_send_provider_alert_webhook_posts_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        client.alerting_config,
        "llm_fallback_alert_webhook_url",
        "http://localhost:9999/webhook",
    )
    monkeypatch.setattr(
        client.alerting_config,
        "llm_fallback_alert_timeout_seconds",
        3.5,
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, *, json: dict[str, object], timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(client.httpx, "post", fake_post)

    payload = {"event": "provider_fallback_attempt", "detail": "timeout"}
    client._send_provider_alert_webhook(payload)

    assert captured["url"] == "http://localhost:9999/webhook"
    assert captured["json"] == payload
    assert captured["timeout"] == 3.5


def test_send_provider_alert_webhook_logs_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        client.alerting_config,
        "llm_fallback_alert_webhook_url",
        "http://localhost:9999/webhook",
    )

    warnings: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        client.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )

    def fake_post(url: str, *, json: dict[str, object], timeout: float):
        raise RuntimeError("down")

    monkeypatch.setattr(client.httpx, "post", fake_post)

    client._send_provider_alert_webhook({"event": "provider_fallback_attempt"})

    assert warnings
    assert "webhook delivery failed" in warnings[0][0]


@pytest.mark.anyio
async def test_generate_local_answer_maps_request_error(monkeypatch):
    request = client.httpx.Request("POST", "http://local")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, json: dict[str, object]):
            raise client.httpx.RequestError("bad request", request=request)

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_local_answer("prompt")

    assert exc_info.value.provider == "local"


@pytest.mark.anyio
async def test_generate_cloud_answer_maps_connect_error(monkeypatch):
    request = client.httpx.Request("POST", "http://cloud")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(
            self, url: str, json: dict[str, object], headers: dict[str, str]
        ):
            raise client.httpx.ConnectError("down", request=request)

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_cloud_answer("prompt")

    assert exc_info.value.provider == "cloud"
    assert exc_info.value.retryable is True


@pytest.mark.anyio
async def test_generate_cloud_answer_maps_timeout(monkeypatch):
    request = client.httpx.Request("POST", "http://cloud")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ):
            raise client.httpx.TimeoutException("slow", request=request)

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_cloud_answer("prompt")

    assert exc_info.value.provider == "cloud"


@pytest.mark.anyio
async def test_generate_cloud_answer_success_without_api_key(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "cloud answer"}}]}

    captured_headers: list[dict[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ):
            captured_headers.append(headers)
            return FakeResponse()

    monkeypatch.setattr(client.cloud_llm_config, "api_key", "")
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    answer = await client._generate_cloud_answer("prompt")

    assert answer == "cloud answer"
    assert captured_headers == [{}]


@pytest.mark.anyio
async def test_generate_cloud_answer_includes_auth_header(monkeypatch):
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "cloud answer"}}]}

    captured_headers: list[dict[str, str]] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ):
            captured_headers.append(headers)
            return FakeResponse()

    monkeypatch.setattr(client.cloud_llm_config, "api_key", "secret")
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    await client._generate_cloud_answer("prompt")

    assert captured_headers == [{"Authorization": "Bearer secret"}]


@pytest.mark.anyio
async def test_generate_cloud_answer_maps_http_status(monkeypatch):
    request = client.httpx.Request("POST", "http://cloud")
    response = client.httpx.Response(400, request=request)

    class FakeResponse:
        def raise_for_status(self) -> None:
            raise client.httpx.HTTPStatusError(
                "bad", request=request, response=response
            )

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ):
            return FakeResponse()

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_cloud_answer("prompt")

    assert exc_info.value.provider == "cloud"
    assert exc_info.value.retryable is False


@pytest.mark.anyio
async def test_generate_cloud_answer_maps_request_error(monkeypatch):
    request = client.httpx.Request("POST", "http://cloud")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(
            self,
            url: str,
            json: dict[str, object],
            headers: dict[str, str],
        ):
            raise client.httpx.RequestError("bad request", request=request)

    monkeypatch.setattr(client.httpx, "AsyncClient", lambda timeout: FakeClient())

    with pytest.raises(client.ProviderRequestError) as exc_info:
        await client._generate_cloud_answer("prompt")

    assert exc_info.value.provider == "cloud"


@pytest.mark.anyio
async def test_generate_answer_raises_for_empty_response(monkeypatch):
    async def empty_local(prompt: str, max_tokens=None) -> str:
        return ""

    async def empty_cloud(prompt: str, max_tokens=None) -> str:
        return ""

    monkeypatch.setattr(client, "_call_local_model", empty_local)
    monkeypatch.setattr(client, "_call_cloud_model", empty_cloud)

    with pytest.raises(client.ModelGenerationError, match="empty response"):
        await client.generate_answer("prompt", provider="local")


@pytest.mark.anyio
async def test_call_model_wrappers_delegate(monkeypatch):
    async def fake_local(prompt: str, max_tokens=None) -> str:
        return "local"

    async def fake_cloud(prompt: str, max_tokens=None) -> str:
        return "cloud"

    monkeypatch.setattr(client, "_generate_local_answer", fake_local)
    monkeypatch.setattr(client, "_generate_cloud_answer", fake_cloud)

    assert await client._call_local_model("prompt") == "local"
    assert await client._call_cloud_model("prompt") == "cloud"


def test_extract_chat_completion_text_returns_empty_for_empty_choices() -> None:
    assert client._extract_chat_completion_text({"choices": []}) == ""
    assert client._extract_chat_completion_text({}) == ""

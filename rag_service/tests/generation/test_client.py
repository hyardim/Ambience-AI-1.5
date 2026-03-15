import pytest

from src.generation import client


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
async def test_generate_answer_raises_when_both_fail(monkeypatch):
    async def fail_cloud(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise RuntimeError("cloud down")

    async def fail_local(prompt: str, max_tokens=None) -> str:  # noqa: ANN001
        raise RuntimeError("local down")

    monkeypatch.setattr(client, "_call_local_model", fail_local)
    monkeypatch.setattr(client, "_call_cloud_model", fail_cloud)

    with pytest.raises(RuntimeError, match="All model providers failed"):
        await client.generate_answer(
            "prompt",
            max_tokens=64,
            provider="cloud",
        )

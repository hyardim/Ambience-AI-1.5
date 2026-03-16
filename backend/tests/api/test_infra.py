from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from src.api import deps, health, rag, router
from src.app import create_app
from src.core import security
from src.db.models import UserRole


def test_health_route_returns_expected_payload():
    assert health.health_check() == {"status": "healthy", "system": "Ambience-AI-1.5"}


def test_api_router_registers_expected_paths():
    paths = {route.path for route in router.api_router.routes}
    assert "/health" in paths
    assert "/search" in paths
    assert "/auth/login" in paths
    assert "/chats/" in paths


def test_create_app_builds_fastapi_app(monkeypatch):
    called = {"logging": 0, "db": 0}

    monkeypatch.setattr(
        "src.app.configure_logging", lambda: called.__setitem__("logging", 1)
    )
    monkeypatch.setattr("src.app.prepare_database", lambda: called.__setitem__("db", 1))

    app = create_app()
    client = TestClient(app)
    response = client.get("/")

    assert called == {"logging": 1, "db": 1}
    assert response.status_code == 200
    assert response.json() == {"status": "Ambience Backend Running"}


def test_main_exposes_app(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("src.app.create_app", lambda: sentinel)
    import importlib

    import src.main as main

    reloaded = importlib.reload(main)
    assert reloaded.app is sentinel


@pytest.mark.asyncio
async def test_rag_search_proxy_success(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"results": [1]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            assert url.endswith("/query")
            assert json["query"] == "query"
            assert json["specialty"] == "neurology"
            return FakeResponse()

    monkeypatch.setattr("src.api.rag.httpx.AsyncClient", FakeClient)
    result = await rag.search_clinical_guidelines(
        "query", "neurology", current_user="user@nhs.uk"
    )
    assert result == {"results": [1]}


@pytest.mark.asyncio
async def test_rag_search_proxy_connection_error(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("src.api.rag.httpx.AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as exc:
        await rag.search_clinical_guidelines("query", current_user="user@nhs.uk")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_rag_search_proxy_timeout(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            raise httpx.TimeoutException("slow")

    monkeypatch.setattr("src.api.rag.httpx.AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as exc:
        await rag.search_clinical_guidelines("query", current_user="user@nhs.uk")
    assert exc.value.status_code == 504


@pytest.mark.asyncio
async def test_rag_search_proxy_non_200(monkeypatch):
    class FakeResponse:
        status_code = 503
        text = "down"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            return FakeResponse()

    monkeypatch.setattr("src.api.rag.httpx.AsyncClient", FakeClient)
    with pytest.raises(HTTPException) as exc:
        await rag.search_clinical_guidelines("query", current_user="user@nhs.uk")
    assert exc.value.status_code == 503
    assert exc.value.detail == "down"


def test_get_current_user_obj_raises_401_when_user_missing(monkeypatch):
    monkeypatch.setattr(deps.user_repository, "get_by_email", lambda db, email: None)
    with pytest.raises(HTTPException) as exc:
        deps.get_current_user_obj(db=object(), email="missing@example.com")
    assert exc.value.status_code == 401


def test_get_admin_user_raises_401_when_user_missing(monkeypatch):
    monkeypatch.setattr(deps.user_repository, "get_by_email", lambda db, email: None)
    with pytest.raises(HTTPException) as exc:
        deps.get_admin_user(db=object(), email="missing@example.com")
    assert exc.value.status_code == 401


def test_get_specialist_user_raises_401_when_user_missing(monkeypatch):
    monkeypatch.setattr(deps.user_repository, "get_by_email", lambda db, email: None)
    with pytest.raises(HTTPException) as exc:
        deps.get_specialist_user(db=object(), email="missing@example.com")
    assert exc.value.status_code == 401


def test_get_admin_user_rejects_wrong_role(monkeypatch):
    user = SimpleNamespace(role=UserRole.GP)
    monkeypatch.setattr(deps.user_repository, "get_by_email", lambda db, email: user)
    with pytest.raises(HTTPException) as exc:
        deps.get_admin_user(db=object(), email="gp@example.com")
    assert exc.value.status_code == 403


def test_get_specialist_user_rejects_wrong_role(monkeypatch):
    user = SimpleNamespace(role=UserRole.ADMIN)
    monkeypatch.setattr(deps.user_repository, "get_by_email", lambda db, email: user)
    with pytest.raises(HTTPException) as exc:
        deps.get_specialist_user(db=object(), email="admin@example.com")
    assert exc.value.status_code == 403


def test_stream_endpoint_rejects_token_without_subject(
    client, created_chat, monkeypatch
):
    monkeypatch.setattr(
        security,
        "decode_token",
        lambda token: (_ for _ in ()).throw(
            HTTPException(status_code=401, detail="bad")
        ),
    )
    response = client.get(f"/chats/{created_chat['id']}/stream?token=bad")
    assert response.status_code == 401


def test_stream_endpoint_rejects_missing_user_after_token_decode(
    client, created_chat, monkeypatch
):
    monkeypatch.setattr(security, "decode_token", lambda token: "missing@example.com")
    monkeypatch.setattr(
        "src.api.chats.user_repository.get_by_email", lambda db, email: None
    )
    response = client.get(f"/chats/{created_chat['id']}/stream?token=good")
    assert response.status_code == 401


def test_logout_route_returns_service_payload(client, gp_headers):
    response = client.post("/auth/logout", headers=gp_headers)
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out successfully"}


def test_admin_guideline_upload_uses_plain_text_error_detail(
    client, admin_headers, monkeypatch
):
    class FakeResponse:
        status_code = 500
        text = "plain failure"

        def json(self):
            raise ValueError("not json")

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.api.admin.httpx.AsyncClient", FakeClient)
    response = client.post(
        "/admin/guidelines/upload",
        headers=admin_headers,
        data={"source_name": "NICE"},
        files={"file": ("guide.pdf", b"pdf-bytes", "application/pdf")},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "plain failure"

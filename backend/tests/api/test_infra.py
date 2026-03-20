from __future__ import annotations

import sys
import types
import warnings
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import deps, router
from src.api.endpoints import health, rag
from src.app.main import create_app
from src.core import config as core_config
from src.core import rate_limit
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
    called = {"logging": 0, "db": 0, "settings": 0}

    monkeypatch.setattr(
        "src.app.main.configure_logging", lambda: called.__setitem__("logging", 1)
    )
    monkeypatch.setattr(
        "src.app.main.prepare_database", lambda: called.__setitem__("db", 1)
    )
    monkeypatch.setattr(
        "src.app.main.validate_settings", lambda: called.__setitem__("settings", 1)
    )

    app = create_app()
    client = TestClient(app)
    response = client.get("/")

    assert called == {"logging": 1, "db": 1, "settings": 1}
    assert response.status_code == 200
    assert response.json() == {"status": "Ambience Backend Running"}


def test_main_exposes_app(monkeypatch):
    sentinel = object()
    monkeypatch.setattr("src.app.main.create_app", lambda: sentinel)
    import importlib

    import src.main as main

    reloaded = importlib.reload(main)
    assert reloaded.app is sentinel


def test_validate_settings_warns_for_insecure_secret(monkeypatch, caplog):
    warnings_seen = []

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(
        core_config.settings, "SECRET_KEY", "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD"
    )
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level("WARNING", logger="backend.config"):
            core_config.validate_settings()
        warnings_seen.extend(caught)

    assert warnings_seen
    assert "insecure default value" in str(warnings_seen[0].message)
    assert "SECRET_KEY is using the insecure default" in caplog.text


def test_validate_settings_is_silent_for_custom_secret(monkeypatch, caplog):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with caplog.at_level("WARNING", logger="backend.config"):
            core_config.validate_settings()

    assert caught == []
    assert caplog.text == ""


def test_validate_settings_rejects_insecure_secret_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(
        core_config.settings, "SECRET_KEY", "TEST_SECRET_KEY_DO_NOT_USE_IN_PROD"
    )
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)

    with pytest.raises(RuntimeError, match="set SECRET_KEY"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


def test_validate_settings_rejects_demo_bootstrap_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", True)

    with pytest.raises(RuntimeError, match="disable AUTH_BOOTSTRAP_DEMO_USERS"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)


def test_validate_settings_rejects_missing_demo_passwords(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", True)
    monkeypatch.setattr(core_config.settings, "DEMO_GP_PASSWORD", "")
    monkeypatch.setattr(core_config.settings, "DEMO_SPECIALIST_PASSWORD", "")
    monkeypatch.setattr(core_config.settings, "DEMO_ADMIN_PASSWORD", "")

    with pytest.raises(RuntimeError, match="Missing: DEMO_GP_PASSWORD"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)


def test_validate_settings_rejects_multi_worker_sse_config(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setenv("WEB_CONCURRENCY", "2")

    with pytest.raises(RuntimeError, match="SSE requires a single backend worker"):
        core_config.validate_settings()

    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)


def test_validate_settings_rejects_non_integer_worker_count(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setenv("WEB_CONCURRENCY", "many")

    with pytest.raises(RuntimeError, match="must be an integer"):
        core_config.validate_settings()

    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)


def test_validate_settings_rejects_localhost_cors_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")
    monkeypatch.setattr(
        core_config.settings, "ALLOWED_ORIGINS", ["http://localhost:3000"]
    )

    with pytest.raises(RuntimeError, match="localhost CORS origins"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


def test_validate_settings_rejects_empty_origins_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")
    monkeypatch.setattr(core_config.settings, "ALLOWED_ORIGINS", [])

    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS must be set"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


def test_validate_settings_rejects_wildcard_origin_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")
    monkeypatch.setattr(core_config.settings, "ALLOWED_ORIGINS", ["*"])

    with pytest.raises(RuntimeError, match="wildcard CORS origins"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


def test_validate_settings_rejects_wildcard_methods_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")
    monkeypatch.setattr(
        core_config.settings, "ALLOWED_ORIGINS", ["https://app.example.com"]
    )
    monkeypatch.setattr(core_config.settings, "CORS_ALLOW_METHODS", ["*"])

    with pytest.raises(RuntimeError, match="wildcard CORS methods"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(
        core_config.settings,
        "CORS_ALLOW_METHODS",
        ["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    )


def test_validate_settings_rejects_wildcard_headers_in_production(monkeypatch):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")
    monkeypatch.setattr(
        core_config.settings, "ALLOWED_ORIGINS", ["https://app.example.com"]
    )
    monkeypatch.setattr(core_config.settings, "CORS_ALLOW_HEADERS", ["*"])

    with pytest.raises(RuntimeError, match="wildcard CORS headers"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")
    monkeypatch.setattr(
        core_config.settings,
        "CORS_ALLOW_HEADERS",
        ["Authorization", "Content-Type", "Idempotency-Key"],
    )


def test_validate_settings_rejects_placeholder_database_url_in_production(
    monkeypatch,
):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings, "ALLOWED_ORIGINS", ["https://app.example.com"]
    )
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:CHANGE_ME_DB_PASSWORD@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


def test_validate_settings_rejects_placeholder_token_pepper_in_production(
    monkeypatch,
):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings, "ALLOWED_ORIGINS", ["https://app.example.com"]
    )
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings,
        "EMAIL_VERIFICATION_TOKEN_PEPPER",
        "CHANGE_ME_VERIFICATION_PEPPER",
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "pepper")

    with pytest.raises(RuntimeError, match="EMAIL_VERIFICATION_TOKEN_PEPPER"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


def test_validate_settings_rejects_empty_password_reset_pepper_in_production(
    monkeypatch,
):
    monkeypatch.setattr(core_config.settings, "APP_ENV", "production")
    monkeypatch.setattr(core_config.settings, "SECRET_KEY", "a-strong-secret")
    monkeypatch.setattr(core_config.settings, "AUTH_BOOTSTRAP_DEMO_USERS", False)
    monkeypatch.setattr(
        core_config.settings, "ALLOWED_ORIGINS", ["https://app.example.com"]
    )
    monkeypatch.setattr(
        core_config.settings,
        "DATABASE_URL",
        "postgresql://admin:secure-password@db:5432/app",
    )
    monkeypatch.setattr(
        core_config.settings, "EMAIL_VERIFICATION_TOKEN_PEPPER", "pepper"
    )
    monkeypatch.setattr(core_config.settings, "PASSWORD_RESET_TOKEN_PEPPER", "")

    with pytest.raises(RuntimeError, match="PASSWORD_RESET_TOKEN_PEPPER"):
        core_config.validate_settings()

    monkeypatch.setattr(core_config.settings, "APP_ENV", "development")


@pytest.mark.asyncio
async def test_rate_limit_dependency_increments_when_under_limit(monkeypatch):
    calls = []

    class FakePipe:
        def incr(self, key):
            calls.append(("incr", key))
            return self

        def expire(self, key, ttl):
            calls.append(("expire", key, ttl))
            return self

        def execute(self):
            calls.append(("execute",))
            return None

    class FakeRedis:
        def get(self, key):
            assert key == "ratelimit:anon:127.0.0.1"
            return "1"

        def pipeline(self):
            return FakePipe()

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: FakeRedis())
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    await rate_limit.rate_limit_dependency(request)

    assert calls == [
        ("incr", "ratelimit:anon:127.0.0.1"),
        ("expire", "ratelimit:anon:127.0.0.1", 60),
        ("execute",),
    ]


@pytest.mark.asyncio
async def test_rate_limit_dependency_keys_by_session_and_ip(monkeypatch):
    seen = {}

    class FakePipe:
        def incr(self, key):
            seen["key"] = key
            return self

        def expire(self, key, ttl):
            return self

        def execute(self):
            return None

    class FakeRedis:
        def get(self, key):
            return None

        def pipeline(self):
            return FakePipe()

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: FakeRedis())
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"authorization": "Bearer demo-token"},
        cookies={},
    )

    await rate_limit.rate_limit_dependency(request)

    assert seen["key"].startswith("ratelimit:session:")
    assert seen["key"].endswith(":127.0.0.1")


@pytest.mark.asyncio
async def test_rate_limit_dependency_uses_access_cookie_subject(monkeypatch):
    seen = {}

    class FakePipe:
        def incr(self, key):
            seen["key"] = key
            return self

        def expire(self, key, ttl):
            return self

        def execute(self):
            return None

    class FakeRedis:
        def get(self, key):
            return None

        def pipeline(self):
            return FakePipe()

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: FakeRedis())
    request = SimpleNamespace(
        client=SimpleNamespace(host="10.0.0.1"),
        headers={},
        cookies={core_config.settings.ACCESS_COOKIE_NAME: "cookie-token"},
    )

    await rate_limit.rate_limit_dependency(request)

    assert seen["key"].startswith("ratelimit:session:")
    assert seen["key"].endswith(":10.0.0.1")


@pytest.mark.asyncio
async def test_rate_limit_dependency_blocks_when_limit_reached(monkeypatch):
    class FakeRedis:
        def get(self, key):
            return str(core_config.settings.RATE_LIMIT_PER_MINUTE)

        def ttl(self, key):
            return 12

    monkeypatch.setattr(rate_limit, "_get_redis", lambda: FakeRedis())
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    with pytest.raises(HTTPException) as exc:
        await rate_limit.rate_limit_dependency(request)

    assert exc.value.status_code == 429
    assert "12 seconds" in exc.value.detail


@pytest.mark.asyncio
async def test_rate_limit_dependency_degrades_gracefully_on_redis_error(monkeypatch):
    class FakeRedis:
        def get(self, key):
            raise RuntimeError("redis down")

    monkeypatch.setattr(rate_limit, "_local_windows", {})
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: FakeRedis())
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    await rate_limit.rate_limit_dependency(request)


@pytest.mark.asyncio
async def test_rate_limit_dependency_allows_request_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(rate_limit, "_local_windows", {})
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    await rate_limit.rate_limit_dependency(request)


@pytest.mark.asyncio
async def test_rate_limit_dependency_blocks_with_local_fallback(monkeypatch):
    monkeypatch.setattr(rate_limit, "_local_windows", {})
    monkeypatch.setattr(core_config.settings, "RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: None)
    request = SimpleNamespace(client=SimpleNamespace(host="192.168.0.10"))

    await rate_limit.rate_limit_dependency(request)
    await rate_limit.rate_limit_dependency(request)

    with pytest.raises(HTTPException) as exc:
        await rate_limit.rate_limit_dependency(request)

    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_dependency_redis_error_uses_local_fallback(monkeypatch):
    class FakeRedis:
        def get(self, key):
            raise RuntimeError("redis down")

    monkeypatch.setattr(rate_limit, "_local_windows", {})
    monkeypatch.setattr(core_config.settings, "RATE_LIMIT_PER_MINUTE", 1)
    monkeypatch.setattr(rate_limit, "_get_redis", lambda: FakeRedis())
    request = SimpleNamespace(client=SimpleNamespace(host="192.168.0.11"))

    await rate_limit.rate_limit_dependency(request)

    with pytest.raises(HTTPException) as exc:
        await rate_limit.rate_limit_dependency(request)

    assert exc.value.status_code == 429


def test_get_redis_returns_none_when_cache_disabled(monkeypatch):
    monkeypatch.setattr(core_config.settings, "CACHE_ENABLED", False)
    monkeypatch.setattr(rate_limit, "_redis_client", None)
    monkeypatch.setattr(rate_limit, "_redis_init_attempted", False)

    assert rate_limit._get_redis() is None


def test_get_redis_initialises_and_caches_client(monkeypatch):
    pinged = {"value": 0}

    class FakeClient:
        def ping(self):
            pinged["value"] += 1

    client = FakeClient()

    class FakeRedisClass:
        @staticmethod
        def from_url(url, decode_responses, socket_connect_timeout):
            assert decode_responses is True
            assert socket_connect_timeout == 2
            return client

    monkeypatch.setattr(core_config.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(rate_limit, "_redis_client", None)
    monkeypatch.setattr(rate_limit, "_redis_init_attempted", False)
    monkeypatch.setitem(
        sys.modules, "redis", types.SimpleNamespace(Redis=FakeRedisClass)
    )

    assert rate_limit._get_redis() is client
    assert rate_limit._get_redis() is client
    assert pinged["value"] == 1


def test_get_redis_logs_and_returns_none_on_failure(monkeypatch, caplog):
    class FakeRedisClass:
        @staticmethod
        def from_url(url, decode_responses, socket_connect_timeout):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(core_config.settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(rate_limit, "_redis_client", None)
    monkeypatch.setattr(rate_limit, "_redis_init_attempted", False)
    monkeypatch.setitem(
        sys.modules, "redis", types.SimpleNamespace(Redis=FakeRedisClass)
    )

    with caplog.at_level("WARNING"):
        assert rate_limit._get_redis() is None

    assert "rate limiting disabled" in caplog.text


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

    monkeypatch.setattr("src.api.endpoints.rag.httpx.AsyncClient", FakeClient)
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

    monkeypatch.setattr("src.api.endpoints.rag.httpx.AsyncClient", FakeClient)
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

    monkeypatch.setattr("src.api.endpoints.rag.httpx.AsyncClient", FakeClient)
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

    monkeypatch.setattr("src.api.endpoints.rag.httpx.AsyncClient", FakeClient)
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


def test_stream_endpoint_rejects_query_token_auth(client, created_chat):
    response = client.get(f"/chats/{created_chat['id']}/stream?token=bad")
    assert response.status_code == 401


def test_stream_endpoint_rejects_missing_credentials(client, created_chat):
    response = client.get(f"/chats/{created_chat['id']}/stream")
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

    monkeypatch.setattr("src.api.endpoints.admin.httpx.AsyncClient", FakeClient)
    response = client.post(
        "/admin/guidelines/upload",
        headers=admin_headers,
        data={"source_name": "NICE"},
        files={"file": ("guide.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "plain failure"


def test_admin_guideline_upload_rejects_non_pdf_signature(client, admin_headers):
    response = client.post(
        "/admin/guidelines/upload",
        headers=admin_headers,
        data={"source_name": "NICE"},
        files={"file": ("guide.pdf", b"not-a-pdf", "application/pdf")},
    )

    assert response.status_code == 415


def test_admin_guideline_upload_rejects_oversized_file(client, admin_headers):
    response = client.post(
        "/admin/guidelines/upload",
        headers=admin_headers,
        data={"source_name": "NICE"},
        files={
            "file": (
                "guide.pdf",
                b"%PDF-1.4\n" + (b"A" * (3 * 1024 * 1024)),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413

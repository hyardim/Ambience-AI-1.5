from datetime import datetime
from types import SimpleNamespace

from src.db.models import ChatStatus
from src.services import chat_service


def test_list_chats_cache_hit_uses_cached_data(monkeypatch):
    cached = [
        {
            "id": 1,
            "title": "Cached Chat",
            "status": "open",
            "specialty": None,
            "severity": None,
            "patient_age": None,
            "patient_gender": None,
            "patient_notes": None,
            "specialist_id": None,
            "assigned_at": None,
            "reviewed_at": None,
            "review_feedback": None,
            "created_at": "2024-01-01T00:00:00",
            "user_id": 7,
        }
    ]

    def fake_get_sync(*_args, **_kwargs):
        return cached

    def fake_list_for_user(*_args, **_kwargs):
        raise AssertionError("repo should not be called when cache hits")

    monkeypatch.setattr(chat_service.cache, "get_sync", fake_get_sync)
    monkeypatch.setattr(chat_service.chat_repository,
                        "list_for_user", fake_list_for_user)

    user = SimpleNamespace(id=7)
    result = chat_service.list_chats(db=None, user=user)
    assert result[0].title == "Cached Chat"


def test_list_chats_cache_miss_sets_cache(monkeypatch):
    captured = {"set": False}

    def fake_get_sync(*_args, **_kwargs):
        return None

    def fake_set_sync(*_args, **_kwargs):
        captured["set"] = True
        return True

    fake_chat = SimpleNamespace(
        id=2,
        title="Fresh Chat",
        status=ChatStatus.OPEN,
        specialty=None,
        severity=None,
        patient_age=None,
        patient_gender=None,
        patient_notes=None,
        specialist_id=None,
        assigned_at=None,
        reviewed_at=None,
        review_feedback=None,
        created_at=datetime(2024, 1, 1),
        user_id=11,
    )

    monkeypatch.setattr(chat_service.cache, "get_sync", fake_get_sync)
    monkeypatch.setattr(chat_service.cache, "set_sync", fake_set_sync)
    monkeypatch.setattr(chat_service.chat_repository,
                        "list_for_user", lambda *_args, **_kwargs: [fake_chat])

    user = SimpleNamespace(id=11)
    result = chat_service.list_chats(db=None, user=user)
    assert result[0].title == "Fresh Chat"
    assert captured["set"] is True


def test_get_chat_cache_hit_skips_db(monkeypatch):
    cached = {
        "id": 3,
        "title": "Cached Detail",
        "status": "open",
        "specialty": None,
        "severity": None,
        "patient_age": None,
        "patient_gender": None,
        "patient_notes": None,
        "specialist_id": None,
        "assigned_at": None,
        "reviewed_at": None,
        "review_feedback": None,
        "created_at": "2024-01-01T00:00:00",
        "user_id": 5,
        "messages": [],
        "files": [],
    }

    def fake_get_sync(*_args, **_kwargs):
        return cached

    def fake_get(*_args, **_kwargs):
        raise AssertionError("repo should not be called when cache hits")

    monkeypatch.setattr(chat_service.cache, "get_sync", fake_get_sync)
    monkeypatch.setattr(chat_service.chat_repository, "get", fake_get)

    user = SimpleNamespace(id=5)
    result = chat_service.get_chat(db=None, user=user, chat_id=3)
    assert result.title == "Cached Detail"


def test_create_chat_invalidates_list_cache(monkeypatch):
    captured = {"pattern": None}

    def fake_delete_pattern_sync(pattern, *_args, **_kwargs):
        captured["pattern"] = pattern
        return 1

    fake_chat = SimpleNamespace(
        id=4,
        title="New Chat",
        status=ChatStatus.OPEN,
        specialty="neuro",
        severity=None,
        patient_age=None,
        patient_gender=None,
        patient_notes=None,
        specialist_id=None,
        assigned_at=None,
        reviewed_at=None,
        review_feedback=None,
        created_at=datetime(2024, 1, 1),
        user_id=9,
    )

    monkeypatch.setattr(chat_service.chat_repository,
                        "create", lambda *_args, **_kwargs: fake_chat)
    monkeypatch.setattr(chat_service.audit_repository,
                        "log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat_service.cache,
                        "delete_pattern_sync", fake_delete_pattern_sync)

    user = SimpleNamespace(id=9)
    payload = SimpleNamespace(
        title="New Chat",
        specialty="neuro",
        severity=None,
        patient_age=None,
        patient_gender=None,
        patient_notes=None,
    )

    result = chat_service.create_chat(db=None, user=user, data=payload)
    assert result.title == "New Chat"
    assert captured["pattern"] is not None

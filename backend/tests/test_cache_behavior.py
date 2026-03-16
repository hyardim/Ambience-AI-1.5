from datetime import datetime
from types import SimpleNamespace

from src.db.models import ChatStatus
from src.services import admin_service
from src.services import chat_service
from src.services import specialist_service


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


def test_specialist_queue_cache_hit_uses_cached_data(monkeypatch):
    cached = [
        {
            "id": 1,
            "title": "Queued Chat",
            "status": "submitted",
            "specialty": "neurology",
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

    monkeypatch.setattr(specialist_service.cache, "get_sync", lambda *_a, **_k: cached)

    specialist = SimpleNamespace(id=5, specialty="neurology")
    result = specialist_service.get_queue(db=None, specialist=specialist)
    assert result[0].title == "Queued Chat"


def test_admin_stats_cache_hit_uses_cached_data(monkeypatch):
    cached = {
        "total_ai_responses": 1,
        "rag_grounded_responses": 1,
        "specialist_responses": 0,
        "active_consultations": 1,
        "chats_by_status": {"submitted": 1},
        "chats_by_specialty": {"neurology": 1},
        "active_users_by_role": {"gp": 1},
        "daily_ai_queries": [],
    }

    monkeypatch.setattr(admin_service.cache, "get_sync", lambda *_a, **_k: cached)

    result = admin_service.get_stats(db=None)
    assert result == cached


def test_list_notifications_cache_hit_uses_cached_data(monkeypatch):
    from src.services import notification_service

    cached = [
        {
            "id": 1,
            "type": "chat_assigned",
            "title": "Assigned",
            "body": "A specialist picked this up",
            "chat_id": 4,
            "is_read": False,
            "created_at": "2024-01-01T00:00:00",
        }
    ]

    monkeypatch.setattr(notification_service.cache, "get_sync", lambda *_a, **_k: cached)
    monkeypatch.setattr(
        notification_service.notification_repository,
        "list_for_user",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("repo should not be called when cache hits")),
    )

    user = SimpleNamespace(id=7)
    result = notification_service.list_notifications(db=None, user=user)
    assert result[0].title == "Assigned"


def test_notification_unread_count_cache_hit_uses_cached_data(monkeypatch):
    from src.services import notification_service

    monkeypatch.setattr(
        notification_service.cache,
        "get_sync",
        lambda *_a, **_k: {"unread_count": 4},
    )
    monkeypatch.setattr(
        notification_service.notification_repository,
        "count_unread",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("repo should not be called when cache hits")),
    )

    user = SimpleNamespace(id=7)
    result = notification_service.get_unread_count(db=None, user=user)
    assert result == {"unread_count": 4}


def test_admin_chat_list_cache_hit_uses_cached_data(monkeypatch):
    cached = [
        {
            "id": 2,
            "title": "Admin Cached Chat",
            "status": "open",
            "specialty": "neurology",
            "severity": None,
            "patient_age": None,
            "patient_gender": None,
            "patient_notes": None,
            "specialist_id": None,
            "assigned_at": None,
            "reviewed_at": None,
            "review_feedback": None,
            "created_at": "2024-01-01T00:00:00",
            "user_id": 9,
            "owner_identifier": "gp_9",
            "specialist_identifier": None,
        }
    ]

    monkeypatch.setattr(admin_service.cache, "get_sync", lambda *_a, **_k: cached)
    result = admin_service.list_all_chats(db=None)
    assert result == cached


def test_admin_audit_logs_cache_hit_uses_cached_data(monkeypatch):
    cached = [
        {
            "id": 1,
            "user_id": 3,
            "user_identifier": "gp_3",
            "action": "REGISTER",
            "category": "AUTH",
            "details": None,
            "timestamp": "2024-01-01T00:00:00",
        }
    ]

    monkeypatch.setattr(admin_service.cache, "get_sync", lambda *_a, **_k: cached)
    result = admin_service.list_audit_logs(db=None)
    assert result == cached

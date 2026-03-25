from src.utils.cache import CacheKeys, cache_keys


def test_chat_list_key_includes_filters():
    key = cache_keys.chat_list(
        user_id=3, page=1, page_size=20, status="open", specialty="neuro"
    )
    assert key == "cache:user:3:chats:open:neuro:1:20"


def test_chat_list_key_defaults_to_all():
    key = cache_keys.chat_list(user_id=9, page=0, page_size=50)
    assert key == "cache:user:9:chats:all:all:0:50"


def test_chat_detail_key_and_patterns():
    detail = cache_keys.chat_detail(user_id=7, chat_id=42)
    detail_pattern = cache_keys.chat_detail_pattern(chat_id=42)
    list_pattern = cache_keys.chat_list_pattern(user_id=7)

    assert detail == "cache:user:7:chat:42"
    assert detail_pattern == "cache:user:*:chat:42"
    assert list_pattern == "cache:user:7:chats:*"


def test_cache_keys_custom_prefix_trims_colon():
    keys = CacheKeys("custom:")
    key = keys.chat_detail(user_id=1, chat_id=2)
    pattern = keys.chat_list_pattern(user_id=1)

    assert key == "custom:user:1:chat:2"
    assert pattern == "custom:user:1:chats:*"


def test_user_profile_key_format():
    key = cache_keys.user_profile(user_id=15)
    assert key == "cache:user:15:profile"


def test_specialist_queue_key_formats():
    assert (
        cache_keys.specialist_queue("neurology") == "cache:specialist:queue:neurology"
    )
    assert cache_keys.specialist_queue() == "cache:specialist:queue:all"
    assert cache_keys.specialist_queue_pattern() == "cache:specialist:queue:*"


def test_specialist_assigned_key_formats():
    assert cache_keys.specialist_assigned(11) == "cache:specialist:11:assigned"
    assert cache_keys.specialist_assigned_pattern() == "cache:specialist:*:assigned"
    assert cache_keys.specialist_assigned_pattern(11) == "cache:specialist:11:assigned"


def test_admin_stats_key_format():
    assert cache_keys.admin_stats() == "cache:admin:stats"


def test_admin_chat_cache_key_formats():
    assert (
        cache_keys.admin_chat_list(
            status="open",
            specialty="neurology",
            user_id=5,
            specialist_id=9,
            skip=10,
            limit=25,
        )
        == "cache:admin:chats:open:neurology:5:9:10:25"
    )
    assert cache_keys.admin_chat_list_pattern() == "cache:admin:chats:*"
    assert cache_keys.admin_chat_detail(12) == "cache:admin:chat:12"
    assert cache_keys.admin_chat_detail_pattern() == "cache:admin:chat:*"


def test_admin_audit_log_and_notification_key_formats():
    assert (
        cache_keys.admin_audit_logs(
            action="REGISTER",
            category="AUTH",
            search="foo bar",
            user_id=3,
            date_from="2024-01-01T00:00:00",
            date_to="2024-01-02T00:00:00",
            limit=50,
        )
        == "cache:admin:logs:REGISTER:AUTH:foo+bar:3:2024-01-01T00:00:00:2024-01-02T00:00:00:50"
    )
    assert cache_keys.admin_audit_logs_pattern() == "cache:admin:logs:*"
    assert cache_keys.notifications(7) == "cache:user:7:notifications:all"
    assert (
        cache_keys.notifications(7, unread_only=True)
        == "cache:user:7:notifications:unread"
    )
    assert cache_keys.notifications_pattern(7) == "cache:user:7:notifications:*"
    assert (
        cache_keys.notifications_unread_count(7)
        == "cache:user:7:notifications:count:unread"
    )

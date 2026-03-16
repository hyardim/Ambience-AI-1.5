from src.utils.cache import CacheKeys, cache_keys


def test_chat_list_key_includes_filters():
    key = cache_keys.chat_list(
        user_id=3, page=1, page_size=20, status="open", specialty="neuro")
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

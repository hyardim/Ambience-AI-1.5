from src.utils.cache import cache, cache_keys


def invalidate_specialist_lists_sync(
    *,
    specialty: str | None = None,
    specialist_id: int | None = None,
) -> None:
    if specialty is not None:
        cache.delete_sync(
            cache_keys.specialist_queue(specialty), resource="specialist_queue"
        )
    cache.delete_pattern_sync(
        cache_keys.specialist_queue_pattern(), resource="specialist_queue"
    )
    if specialist_id is not None:
        cache.delete_sync(
            cache_keys.specialist_assigned(specialist_id),
            user_id=specialist_id,
            resource="specialist_assigned",
        )
    else:
        cache.delete_pattern_sync(
            cache_keys.specialist_assigned_pattern(), resource="specialist_assigned"
        )


def invalidate_admin_stats_sync() -> None:
    cache.delete_sync(cache_keys.admin_stats(), resource="admin_stats")


def invalidate_admin_chat_caches_sync(chat_id: int | None = None) -> None:
    cache.delete_pattern_sync(
        cache_keys.admin_chat_list_pattern(), resource="admin_chat_list"
    )
    cache.delete_pattern_sync(
        cache_keys.admin_chat_detail_pattern(chat_id), resource="admin_chat_detail"
    )


def invalidate_chat_views_sync(*, chat_id: int, user_id: int) -> None:
    cache.delete_pattern_sync(
        cache_keys.chat_detail_pattern(chat_id), user_id=user_id, resource="chat_detail"
    )
    cache.delete_pattern_sync(
        cache_keys.chat_list_pattern(user_id), user_id=user_id, resource="chat_list"
    )


def invalidate_chat_related_sync(
    *,
    chat_id: int,
    user_id: int,
    specialty: str | None = None,
    specialist_id: int | None = None,
) -> None:
    invalidate_chat_views_sync(chat_id=chat_id, user_id=user_id)
    invalidate_specialist_lists_sync(
        specialty=specialty,
        specialist_id=specialist_id,
    )
    invalidate_admin_chat_caches_sync(chat_id)
    invalidate_admin_stats_sync()


async def invalidate_specialist_lists_async(
    *,
    specialty: str | None = None,
    specialist_id: int | None = None,
) -> None:
    if specialty is not None:
        await cache.delete(
            cache_keys.specialist_queue(specialty), resource="specialist_queue"
        )
    await cache.delete_pattern(
        cache_keys.specialist_queue_pattern(), resource="specialist_queue"
    )
    if specialist_id is not None:
        await cache.delete(
            cache_keys.specialist_assigned(specialist_id),
            user_id=specialist_id,
            resource="specialist_assigned",
        )
    else:
        await cache.delete_pattern(
            cache_keys.specialist_assigned_pattern(), resource="specialist_assigned"
        )


async def invalidate_admin_stats_async() -> None:
    await cache.delete(cache_keys.admin_stats(), resource="admin_stats")


async def invalidate_admin_chat_caches_async(chat_id: int | None = None) -> None:
    await cache.delete_pattern(
        cache_keys.admin_chat_list_pattern(), resource="admin_chat_list"
    )
    await cache.delete_pattern(
        cache_keys.admin_chat_detail_pattern(chat_id), resource="admin_chat_detail"
    )


async def invalidate_chat_views_async(*, chat_id: int, user_id: int) -> None:
    await cache.delete_pattern(
        cache_keys.chat_detail_pattern(chat_id), user_id=user_id, resource="chat_detail"
    )
    await cache.delete_pattern(
        cache_keys.chat_list_pattern(user_id), user_id=user_id, resource="chat_list"
    )


async def invalidate_chat_related_async(
    *,
    chat_id: int,
    user_id: int,
    specialty: str | None = None,
    specialist_id: int | None = None,
) -> None:
    await invalidate_chat_views_async(chat_id=chat_id, user_id=user_id)
    await invalidate_specialist_lists_async(
        specialty=specialty,
        specialist_id=specialist_id,
    )
    await invalidate_admin_chat_caches_async(chat_id)
    await invalidate_admin_stats_async()

"""
Centralised authorisation policy for chat access.

Every endpoint that gates access to a chat (detail, stream, upload,
send-message) should call one of these functions instead of implementing
inline ownership / specialist / admin checks.

Rules implemented
-----------------
- **Owner**: the user who created the chat (``chat.user_id == user.id``).
- **Assigned specialist**: ``chat.specialist_id == user.id``.
- **Queue specialist**: a specialist whose specialty matches the chat and
  the chat is in SUBMITTED status (visible in the review queue).
- **Admin**: ``user.role == UserRole.ADMIN`` — full visibility.

The ``can_*`` helpers return ``bool``; the ``require_*`` helpers raise
``HTTPException(403 | 404)`` directly so callers stay lean.
"""

from src.db.models import Chat, ChatStatus, User, UserRole

# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------


def _is_owner(user: User, chat: Chat) -> bool:
    return bool(chat.user_id == user.id)


def _is_assigned_specialist(user: User, chat: Chat) -> bool:
    return bool(
        user.role == UserRole.SPECIALIST
        and chat.specialist_id is not None
        and chat.specialist_id == user.id
    )


def _is_queue_specialist(user: User, chat: Chat) -> bool:
    """Specialist can see chats in SUBMITTED state that match their specialty."""
    if user.role != UserRole.SPECIALIST:
        return False
    if chat.status != ChatStatus.SUBMITTED:
        return False
    # A specialist with no specialty filter sees all submitted chats;
    # otherwise specialty must match.
    if user.specialty and chat.specialty != user.specialty:
        return False
    return True


def _is_admin(user: User) -> bool:
    return bool(user.role == UserRole.ADMIN)


# ---------------------------------------------------------------------------
# Public policy functions
# ---------------------------------------------------------------------------


def can_view_chat(user: User, chat: Chat) -> bool:
    """Can the user read this chat's detail / messages?"""
    return (
        _is_owner(user, chat)
        or _is_assigned_specialist(user, chat)
        or _is_queue_specialist(user, chat)
        or _is_admin(user)
    )


def can_stream_chat(user: User, chat: Chat) -> bool:
    """Can the user subscribe to the SSE stream for this chat?

    Same rules as ``can_view_chat`` — if you can see the chat you may
    also watch the live generation stream.
    """
    return can_view_chat(user, chat)


def can_upload_to_chat(user: User, chat: Chat) -> bool:
    """Can the user attach files to this chat?

    Restricted to the owner and the *assigned* specialist (queue
    specialists cannot upload to chats they haven't claimed yet).
    Admins can also upload.
    """
    return (
        _is_owner(user, chat) or _is_assigned_specialist(user, chat) or _is_admin(user)
    )


def can_send_message(user: User, chat: Chat) -> bool:
    """Can the user post a new message to this chat?

    Same scope as upload — owner, assigned specialist, or admin.
    """
    return (
        _is_owner(user, chat) or _is_assigned_specialist(user, chat) or _is_admin(user)
    )

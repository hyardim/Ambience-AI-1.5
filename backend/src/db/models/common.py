import enum
from datetime import datetime, timezone

ENUM_VALUE_CONFIG = {
    "native_enum": False,
    "values_callable": lambda enum_cls: [member.value for member in enum_cls],
}


def utc_now() -> datetime:
    # DB columns use TIMESTAMP WITHOUT TIME ZONE, so return naive UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(enum.Enum):
    GP = "gp"
    SPECIALIST = "specialist"
    ADMIN = "admin"


class NotificationType(enum.Enum):
    CHAT_ASSIGNED = "chat_assigned"
    SPECIALIST_MSG = "specialist_msg"
    CHAT_APPROVED = "chat_approved"
    CHAT_REJECTED = "chat_rejected"
    CHAT_REVISION = "chat_revision"


class ChatStatus(enum.Enum):
    OPEN = "open"
    SUBMITTED = "submitted"
    ASSIGNED = "assigned"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"
    FLAGGED = "flagged"
    ARCHIVED = "archived"

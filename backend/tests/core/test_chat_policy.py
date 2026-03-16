"""
Tests for the centralised chat authorisation policy.

Covers the role × chat-state matrix for GP, Specialist and Admin across
all policy functions: can_view_chat, can_stream_chat, can_upload_to_chat,
can_send_message.
"""

from types import SimpleNamespace

import pytest
from src.core.chat_policy import (
    can_send_message,
    can_stream_chat,
    can_upload_to_chat,
    can_view_chat,
)
from src.db.models import ChatStatus, UserRole

# ---------------------------------------------------------------------------
# Helpers — lightweight stubs that satisfy the policy functions' attribute
# access without requiring full SQLAlchemy model initialisation.
# ---------------------------------------------------------------------------


def _make_user(
    id: int,
    role: UserRole = UserRole.GP,
    specialty: str | None = None,
):
    return SimpleNamespace(id=id, role=role, specialty=specialty)


def _make_chat(
    id: int = 1,
    user_id: int = 1,
    status: ChatStatus = ChatStatus.OPEN,
    specialty: str | None = None,
    specialist_id: int | None = None,
):
    return SimpleNamespace(
        id=id,
        user_id=user_id,
        status=status,
        specialty=specialty,
        specialist_id=specialist_id,
    )


# Reusable user fixtures
GP_OWNER = _make_user(1, UserRole.GP)
GP_OTHER = _make_user(2, UserRole.GP)
SPEC_NEURO = _make_user(10, UserRole.SPECIALIST, specialty="neurology")
SPEC_CARDIO = _make_user(11, UserRole.SPECIALIST, specialty="cardiology")
SPEC_NO_SPEC = _make_user(12, UserRole.SPECIALIST, specialty=None)
ADMIN = _make_user(20, UserRole.ADMIN)


# ---------------------------------------------------------------------------
# can_view_chat
# ---------------------------------------------------------------------------


class TestCanViewChat:
    # --- Owner ---
    @pytest.mark.parametrize("status", list(ChatStatus))
    def test_owner_can_always_view(self, status):
        chat = _make_chat(user_id=GP_OWNER.id, status=status, specialty="neurology")
        assert can_view_chat(GP_OWNER, chat) is True

    def test_non_owner_gp_cannot_view(self):
        chat = _make_chat(user_id=GP_OWNER.id, status=ChatStatus.OPEN)
        assert can_view_chat(GP_OTHER, chat) is False

    # --- Specialist: queue (SUBMITTED) ---
    def test_specialist_matching_specialty_can_view_submitted(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.SUBMITTED,
            specialty="neurology",
        )
        assert can_view_chat(SPEC_NEURO, chat) is True

    def test_specialist_mismatched_specialty_cannot_view_submitted(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.SUBMITTED,
            specialty="neurology",
        )
        assert can_view_chat(SPEC_CARDIO, chat) is False

    def test_specialist_no_specialty_can_view_any_submitted(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.SUBMITTED,
            specialty="neurology",
        )
        assert can_view_chat(SPEC_NO_SPEC, chat) is True

    def test_specialist_cannot_view_open_unowned(self):
        chat = _make_chat(user_id=1, status=ChatStatus.OPEN, specialty="neurology")
        assert can_view_chat(SPEC_NEURO, chat) is False

    # --- Specialist: assigned ---
    def test_assigned_specialist_can_view(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.ASSIGNED,
            specialist_id=SPEC_NEURO.id,
        )
        assert can_view_chat(SPEC_NEURO, chat) is True

    def test_other_specialist_cannot_view_assigned(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.ASSIGNED,
            specialist_id=SPEC_NEURO.id,
        )
        assert can_view_chat(SPEC_CARDIO, chat) is False

    # --- Admin ---
    @pytest.mark.parametrize("status", list(ChatStatus))
    def test_admin_can_always_view(self, status):
        chat = _make_chat(user_id=1, status=status)
        assert can_view_chat(ADMIN, chat) is True


# ---------------------------------------------------------------------------
# can_stream_chat  (same rules as can_view_chat)
# ---------------------------------------------------------------------------


class TestCanStreamChat:
    def test_owner_can_stream(self):
        chat = _make_chat(user_id=GP_OWNER.id)
        assert can_stream_chat(GP_OWNER, chat) is True

    def test_non_owner_gp_cannot_stream(self):
        chat = _make_chat(user_id=GP_OWNER.id)
        assert can_stream_chat(GP_OTHER, chat) is False

    def test_specialist_matching_queue_can_stream(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.SUBMITTED,
            specialty="neurology",
        )
        assert can_stream_chat(SPEC_NEURO, chat) is True

    def test_specialist_assigned_can_stream(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.ASSIGNED,
            specialist_id=SPEC_NEURO.id,
        )
        assert can_stream_chat(SPEC_NEURO, chat) is True

    def test_admin_can_stream(self):
        chat = _make_chat(user_id=1)
        assert can_stream_chat(ADMIN, chat) is True


# ---------------------------------------------------------------------------
# can_upload_to_chat
# ---------------------------------------------------------------------------


class TestCanUploadToChat:
    def test_owner_can_upload(self):
        chat = _make_chat(user_id=GP_OWNER.id)
        assert can_upload_to_chat(GP_OWNER, chat) is True

    def test_non_owner_gp_cannot_upload(self):
        chat = _make_chat(user_id=GP_OWNER.id)
        assert can_upload_to_chat(GP_OTHER, chat) is False

    def test_assigned_specialist_can_upload(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.ASSIGNED,
            specialist_id=SPEC_NEURO.id,
        )
        assert can_upload_to_chat(SPEC_NEURO, chat) is True

    def test_queue_specialist_cannot_upload(self):
        """A specialist who sees a chat in their queue but hasn't claimed
        it should NOT be able to upload files."""
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.SUBMITTED,
            specialty="neurology",
        )
        assert can_upload_to_chat(SPEC_NEURO, chat) is False

    def test_admin_can_upload(self):
        chat = _make_chat(user_id=1)
        assert can_upload_to_chat(ADMIN, chat) is True

    def test_other_specialist_cannot_upload(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.ASSIGNED,
            specialist_id=SPEC_NEURO.id,
        )
        assert can_upload_to_chat(SPEC_CARDIO, chat) is False


# ---------------------------------------------------------------------------
# can_send_message
# ---------------------------------------------------------------------------


class TestCanSendMessage:
    def test_owner_can_send(self):
        chat = _make_chat(user_id=GP_OWNER.id)
        assert can_send_message(GP_OWNER, chat) is True

    def test_non_owner_gp_cannot_send(self):
        chat = _make_chat(user_id=GP_OWNER.id)
        assert can_send_message(GP_OTHER, chat) is False

    def test_assigned_specialist_can_send(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.ASSIGNED,
            specialist_id=SPEC_NEURO.id,
        )
        assert can_send_message(SPEC_NEURO, chat) is True

    def test_queue_specialist_cannot_send(self):
        chat = _make_chat(
            user_id=1,
            status=ChatStatus.SUBMITTED,
            specialty="neurology",
        )
        assert can_send_message(SPEC_NEURO, chat) is False

    def test_admin_can_send(self):
        chat = _make_chat(user_id=1)
        assert can_send_message(ADMIN, chat) is True

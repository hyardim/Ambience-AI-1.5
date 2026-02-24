"""
Specialist workflow endpoints.

All routes require an authenticated user with role == "specialist".
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from src.db.session import get_db
from src.db.models import Chat, ChatStatus, User, UserRole, AuditLog
from src.core import security
from src.schemas.chat import ChatResponse, AssignRequest, ReviewRequest

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency: specialist-only guard
# ---------------------------------------------------------------------------

def get_specialist_user(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.SPECIALIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only specialists can access this endpoint",
        )
    return user


def _chat_to_response(chat: Chat) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status.value,
        specialty=chat.specialty,
        severity=chat.severity,
        specialist_id=chat.specialist_id,
        assigned_at=chat.assigned_at,
        reviewed_at=chat.reviewed_at,
        review_feedback=chat.review_feedback,
        created_at=chat.created_at.isoformat() if chat.created_at else "",
        user_id=chat.user_id,
    )


# ---------------------------------------------------------------------------
# GET /specialist/queue  — submitted chats matching specialist's specialty
# ---------------------------------------------------------------------------

@router.get("/queue", response_model=List[ChatResponse])
def get_queue(
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    """
    Returns all SUBMITTED chats that match this specialist's specialty.
    If the specialist has no specialty set, returns all submitted chats.
    """
    query = db.query(Chat).filter(Chat.status == ChatStatus.SUBMITTED)

    if specialist.specialty:
        query = query.filter(Chat.specialty == specialist.specialty)

    chats = query.order_by(Chat.created_at.asc()).all()
    return [_chat_to_response(c) for c in chats]


# ---------------------------------------------------------------------------
# GET /specialist/assigned  — chats assigned to this specialist
# ---------------------------------------------------------------------------

@router.get("/assigned", response_model=List[ChatResponse])
def get_assigned(
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    """Returns all chats currently assigned to this specialist."""
    chats = (
        db.query(Chat)
        .filter(
            Chat.specialist_id == specialist.id,
            Chat.status.in_([ChatStatus.ASSIGNED, ChatStatus.REVIEWING]),
        )
        .order_by(Chat.assigned_at.asc())
        .all()
    )
    return [_chat_to_response(c) for c in chats]


# ---------------------------------------------------------------------------
# POST /specialist/chats/{chat_id}/assign  — assign a specialist to a chat
# ---------------------------------------------------------------------------

@router.post("/chats/{chat_id}/assign", response_model=ChatResponse)
def assign_specialist(
    chat_id: int,
    body: AssignRequest,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    """
    Assign a specialist to a submitted chat.
    The requesting specialist can only assign themselves.
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if chat.status != ChatStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"Chat is not in SUBMITTED state (current: {chat.status.value})",
        )

    if body.specialist_id != specialist.id:
        raise HTTPException(
            status_code=403,
            detail="You can only assign yourself to a chat",
        )

    chat.specialist_id = specialist.id
    chat.status = ChatStatus.ASSIGNED
    chat.assigned_at = datetime.utcnow()

    db.add(AuditLog(
        user_id=specialist.id,
        action="ASSIGN_SPECIALIST",
        details=f"Specialist {specialist.email} assigned to chat {chat_id}",
    ))
    db.commit()
    db.refresh(chat)
    return _chat_to_response(chat)


# ---------------------------------------------------------------------------
# POST /specialist/chats/{chat_id}/review  — approve or reject
# ---------------------------------------------------------------------------

@router.post("/chats/{chat_id}/review", response_model=ChatResponse)
def review_chat(
    chat_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    specialist: User = Depends(get_specialist_user),
):
    """
    Approve or reject a chat that is assigned to this specialist.
    action: "approve" | "reject"
    """
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    chat = db.query(Chat).filter(
        Chat.id == chat_id,
        Chat.specialist_id == specialist.id,
    ).first()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found or not assigned to you")

    if chat.status not in (ChatStatus.ASSIGNED, ChatStatus.REVIEWING):
        raise HTTPException(
            status_code=400,
            detail=f"Chat must be ASSIGNED or REVIEWING to review (current: {chat.status.value})",
        )

    chat.status = ChatStatus.APPROVED if body.action == "approve" else ChatStatus.REJECTED
    chat.reviewed_at = datetime.utcnow()
    chat.review_feedback = body.feedback

    db.add(AuditLog(
        user_id=specialist.id,
        action=f"REVIEW_{body.action.upper()}",
        details=f"Chat {chat_id} {body.action}d by {specialist.email}. Feedback: {body.feedback or 'none'}",
    ))
    db.commit()
    db.refresh(chat)
    return _chat_to_response(chat)

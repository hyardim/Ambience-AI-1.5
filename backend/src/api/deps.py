from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core import security
from src.db.models import User, UserRole
from src.db.session import get_db
from src.repositories import user_repository


def _require_user(
    db: Session,
    email: str,
    *,
    required_role: UserRole | None = None,
) -> User:
    """Resolve and validate a user by email, enforcing active status and optional role."""
    user = user_repository.get_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )
    if required_role is not None and user.role != required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {required_role.value}s can access this endpoint",
        )
    return user


def get_current_user_obj(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    return _require_user(db, email)


def get_admin_user(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    return _require_user(db, email, required_role=UserRole.ADMIN)


def get_specialist_user(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    return _require_user(db, email, required_role=UserRole.SPECIALIST)

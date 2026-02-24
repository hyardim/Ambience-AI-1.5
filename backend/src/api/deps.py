from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core import security
from src.db.models import User, UserRole
from src.db.session import get_db
from src.repositories import user_repository


def get_current_user_obj(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    user = user_repository.get_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_specialist_user(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
) -> User:
    user = user_repository.get_by_email(db, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.SPECIALIST:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only specialists can access this endpoint",
        )
    return user

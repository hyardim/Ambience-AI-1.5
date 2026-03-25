from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.db.models import User, UserRole


def _normalise_email(email: str) -> str:
    return email.lower().strip()


def get_by_email(db: Session, email: str) -> Optional[User]:
    """Look up a user by email using case-insensitive matching."""
    return db.query(User).filter(func.lower(User.email) == _normalise_email(email)).first()


def get_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def create(
    db: Session,
    *,
    email: str,
    hashed_password: str,
    full_name: Optional[str] = "New User",
    role: UserRole = UserRole.GP,
    specialty: Optional[str] = None,
    email_verified: bool = True,
    email_verified_at: Optional[datetime] = None,
) -> User:
    user = User(
        email=_normalise_email(email),
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        specialty=specialty,
        email_verified=email_verified,
        email_verified_at=email_verified_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update(db: Session, user: User, **fields) -> User:
    for key, value in fields.items():
        if key == "email" and isinstance(value, str):
            value = _normalise_email(value)
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user

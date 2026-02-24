from typing import Optional
from sqlalchemy.orm import Session

from src.db.models import User, UserRole


def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


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
) -> User:
    user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        specialty=specialty,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update(db: Session, user: User, **fields) -> User:
    for key, value in fields.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user

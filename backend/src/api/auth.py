from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.db.models import User, UserRole, AuditLog
from src.core import security
from src.core.config import settings
from src.schemas.auth import UserRegister, ProfileUpdate, UserOut

router = APIRouter()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_user_or_404(db: Session, email: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _make_token(user: User) -> dict:
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token(
        data={"sub": user.email, "role": user.role.value},
        expires_delta=expires,
    )
    return {"access_token": token, "token_type": "bearer"}


# ---------------------------------------------------------------------------
# POST /auth/login  — existing auto-signup login
# ---------------------------------------------------------------------------

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate with email + password.
    Auto-creates a GP account if the email is not yet registered.
    """
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user:
        user = User(
            email=form_data.username,
            hashed_password=security.get_password_hash(form_data.password),
            full_name="New User",
            role=UserRole.GP,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not security.verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
                headers={"WWW-Authenticate": "Bearer"},
            )

    db.add(AuditLog(user_id=user.id, action="LOGIN", details=user.email))
    db.commit()

    return _make_token(user)


# ---------------------------------------------------------------------------
# POST /auth/register  — explicit registration with role + specialty
# ---------------------------------------------------------------------------

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new account with a specific role.
    Specialists must supply a specialty.
    """
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        role = UserRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")

    if role == UserRole.SPECIALIST and not payload.specialty:
        raise HTTPException(status_code=400, detail="Specialists must provide a specialty")

    user = User(
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=payload.full_name,
        role=role,
        specialty=payload.specialty,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(AuditLog(user_id=user.id, action="REGISTER", details=payload.email))
    db.commit()
    return user


# ---------------------------------------------------------------------------
# GET /auth/me  — current user profile
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
def me(
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
):
    return _get_user_or_404(db, email)


# ---------------------------------------------------------------------------
# PATCH /auth/profile  — update name, specialty, or password
# ---------------------------------------------------------------------------

@router.patch("/profile", response_model=UserOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    email: str = Depends(security.get_current_user),
):
    """Update the authenticated user's profile fields."""
    user = _get_user_or_404(db, email)

    if payload.full_name is not None:
        user.full_name = payload.full_name

    if payload.specialty is not None:
        user.specialty = payload.specialty

    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(status_code=400, detail="current_password is required to set a new password")
        if not security.verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.hashed_password = security.get_password_hash(payload.new_password)

    db.add(AuditLog(user_id=user.id, action="UPDATE_PROFILE", details=email))
    db.commit()
    db.refresh(user)
    return user

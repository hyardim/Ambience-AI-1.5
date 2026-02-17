from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.core import security
from src.db.models import User
from src.db.session import get_db
from src.schemas.auth import AuthResponse, AuthUser, UserRegister

router = APIRouter()

@router.post("/login", response_model=AuthResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Returns a JWT access token if credentials are valid.
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = security.create_access_token(
        data={"sub": user.email, "role": user.role}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        },
    }


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if payload.role == "specialist" and not payload.specialty:
        raise HTTPException(status_code=400, detail="Specialty is required for specialist role")

    full_name = f"{payload.first_name.strip()} {payload.last_name.strip()}".strip()
    new_user = User(
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=full_name,
        role=payload.role,
        specialty=payload.specialty,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = security.create_access_token(
        data={"sub": new_user.email, "role": new_user.role}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role,
        },
    }


@router.get("/me", response_model=AuthUser)
def me(current_user: dict = Depends(security.get_current_user), db: Session = Depends(get_db)):
    email = current_user["email"]
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
    }
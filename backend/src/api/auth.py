from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

# Import our system components
from src.db.session import get_db
from src.db.models import User, UserRole
from src.core import security
from src.core.config import settings

router = APIRouter()

@router.post("/login")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Real Authentication with Auto-Signup.
    If the user exists: Verify password.
    If the user does NOT exist: Create them immediately (Default: GP).
    """
    # 1. Check if user exists in DB
    user = db.query(User).filter(User.email == form_data.username).first()

    # 2. AUTO-SIGNUP (Dev Feature)
    # If user is missing, create them!
    if not user:
        hashed_pw = security.get_password_hash(form_data.password)
        new_user = User(
            email=form_data.username, 
            hashed_password=hashed_pw,
            full_name="New User",
            role=UserRole.GP # Default everyone to GP
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user # Log them in immediately
    
    # 3. If user exists, verify password
    else:
        if not security.verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 4. Create Access Token (With Role!)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # We add the 'role' to the token so the Frontend knows who they are
    access_token = security.create_access_token(
        data={"sub": user.email, "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
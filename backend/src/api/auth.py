from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from src.core import security  # We use the helper functions from here

router = APIRouter()

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    FR7: Simple authentication for GP access.
    Returns a JWT access token if credentials are valid.
    """
    # 1. Prototype credential check (Hardcoded for now)
    # You can use "gp_user" and "password123" or "test@gp.com" / "fake_hash_123"
    valid_user = (form_data.username == "gp_user" and form_data.password == "password123")
    valid_test = (form_data.username == "test@gp.com" and form_data.password == "fake_hash_123")

    if not (valid_user or valid_test):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Create Access Token using the helper function in security.py
    # This handles all the JWT imports and time calculations for you!
    access_token = security.create_access_token(
        data={"sub": form_data.username}
    )
    
    # 3. Return the token
    return {"access_token": access_token, "token_type": "bearer"}
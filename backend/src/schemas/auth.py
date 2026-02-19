from typing import Literal, Optional

from pydantic import BaseModel, EmailStr


UserRole = Literal["gp", "specialist", "admin"]


class AuthUser(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: AuthUser


class UserRegister(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    role: UserRole = "gp"
    specialty: Optional[str] = None

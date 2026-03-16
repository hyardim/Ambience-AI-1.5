from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = "New User"
    role: str = "gp"  # "gp" | "specialist" | "admin"
    specialty: Optional[str] = None  # required when role == "specialist"


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    specialty: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str]
    role: str
    specialty: Optional[str]
    is_active: bool


class PasswordResetRequest(BaseModel):
    email: EmailStr
    new_password: str


class AuthResponse(BaseModel):
    """Returned by login & register — token plus basic user info."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut

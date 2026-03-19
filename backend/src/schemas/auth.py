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
    email_verified: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class EmailVerificationResendRequest(BaseModel):
    email: EmailStr


class EmailVerificationConfirmRequest(BaseModel):
    token: str


class RegisterResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    user: UserOut
    requires_email_verification: bool = False
    message: str


class AuthResponse(BaseModel):
    """Returned by login & register — token plus basic user info."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut

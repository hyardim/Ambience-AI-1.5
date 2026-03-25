import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{}|;:'\",.<>?/`~\\])"
)
_COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "password123!",
    "12345678",
    "qwerty123",
    "welcome1",
    "letmein1",
    "admin123",
    "changeme1",
}


def _validate_password_complexity(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if not _PASSWORD_PATTERN.search(password):
        raise ValueError(
            "Password must contain at least one uppercase letter, "
            "one lowercase letter, one digit, and one special character"
        )
    if password.strip().lower() in _COMMON_PASSWORDS:
        raise ValueError("Password is too common; choose a less predictable password")
    return password


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    full_name: Optional[str] = Field(default="New User", max_length=150)
    role: Literal["gp", "specialist", "admin"] = "gp"
    specialty: Optional[str] = Field(default=None, max_length=100)

    @field_validator("password")
    @classmethod
    def check_password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=150)
    specialty: Optional[str] = Field(default=None, max_length=100)
    current_password: Optional[str] = Field(
        default=None, max_length=PASSWORD_MAX_LENGTH
    )
    new_password: Optional[str] = Field(default=None, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def check_new_password_complexity(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_password_complexity(v)
        return v


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
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    @field_validator("new_password")
    @classmethod
    def check_password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class EmailVerificationResendRequest(BaseModel):
    email: EmailStr


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class RegisterResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    user: UserOut
    requires_email_verification: bool = False
    message: str


class AuthResponse(BaseModel):
    """Returned by login & register -- token plus basic user info."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut

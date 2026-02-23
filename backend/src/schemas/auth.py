from pydantic import BaseModel, EmailStr
from typing import Optional


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = "New User"
    role: str = "gp"                    # "gp" | "specialist" | "admin"
    specialty: Optional[str] = None     # required when role == "specialist"


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    specialty: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    specialty: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True

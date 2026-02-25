import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator, ConfigDict


# --- Pydantic-схеми ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr

    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()

        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")

        if len(v) > 50:
            raise ValueError("Username must be less than 50 characters")

        # Тільки букви, цифри, підкреслення
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username can only contain letters, numbers and underscores")

        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        v = v.strip()

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")

        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

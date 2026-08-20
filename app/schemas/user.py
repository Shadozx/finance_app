from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.schemas.validators import password_validator, username_validator


# --- Pydantic-схеми ---
class UserCreate(BaseModel):
    username: str
    email: EmailStr

    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return username_validator(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return password_validator(v)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UsernameUpdate(BaseModel):
    new_username: str

    @field_validator("new_username")
    @classmethod
    def validate_new_username(cls, v: str) -> str:
        return username_validator(v)


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return password_validator(v)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

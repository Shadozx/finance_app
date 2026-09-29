from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, ValidationInfo, field_validator

from app.core.error_codes import FieldErrorCode
from app.schemas.validators import field_error, password_validator, username_validator


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
    def validate_new_password(cls, v: str, info: ValidationInfo) -> str:
        password = password_validator(v)
        if info.data.get("current_password") == password:
            raise field_error(
                FieldErrorCode.SAME_AS_CURRENT,
                "New password must be different from current password",
            )
        return password


class UserResponse(BaseModel):
    id: int
    username: str
    email: str

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

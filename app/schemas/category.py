from enum import Enum

from pydantic import BaseModel, field_validator, ConfigDict
from datetime import datetime

from app.schemas.validators import name_validator


class CategoryCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return name_validator(v, "Category")


class CategoryUpdate(CategoryCreate):
    pass


class CategoryStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    ALL = "all"


class CategoryResponse(BaseModel):
    id: int
    name: str
    user_id: int
    created_at: datetime
    archived_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

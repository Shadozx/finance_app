from pydantic import BaseModel, field_validator, ConfigDict
from datetime import datetime

# --- Pydantic-схеми ---
class CategoryCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()

        if len(v) < 1:
            raise ValueError("Category name must be at least 1 character")

        if len(v) > 100:
            raise ValueError("Category name must be less than 100 characters")

        return v

class CategoryUpdate(CategoryCreate):
    pass

class CategoryResponse(BaseModel):
    id: int
    name: str
    user_id: int
    created_at: datetime
    archived_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

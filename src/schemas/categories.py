from pydantic import BaseModel
from datetime import datetime

# --- Pydantic-схеми ---
class CategoryCreate(BaseModel):
    name: str

class CategoryOut(CategoryCreate):
    id: int


    model_config = {
        'from_attributes': True
    }



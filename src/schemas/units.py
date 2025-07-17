from pydantic import BaseModel
from datetime import datetime


# --- Pydantic-схеми ---
class UnitCreate(BaseModel):
    name: str


class UnitOut(UnitCreate):

    model_config = {
        'from_attributes': True
    }

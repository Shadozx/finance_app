from pydantic import BaseModel
from datetime import datetime

# --- Pydantic-схеми ---
class UnitCreate(BaseModel):
    amount: float
    type: str  # 'income' або 'expense'
    description: str


class TransactionOut(UnitCreate):
    id: int
    added_at: datetime


    model_config = {
        'from_attributes': True
    }

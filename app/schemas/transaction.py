from pydantic import BaseModel, field_validator, ConfigDict
from datetime import date

from app.models.transaction import TransactionType
from decimal import Decimal

class TransactionCreate(BaseModel):
    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = None

    date: date

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal)->Decimal:
        if v < 0:
            raise ValueError("Amount cannot be negative")

        return v

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, v: str)->str:
        v = v.strip().upper()

        if len(v) != 3:
            raise ValueError("Currency code must be 3 letters")

        return v


class TransactionUpdate(TransactionCreate):
    pass


class TransactionResponse(BaseModel):
    id: int
    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = None

    date: date

    user_id: int

    model_config = ConfigDict(from_attributes=True)


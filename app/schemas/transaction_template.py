from datetime import datetime, date

from pydantic import BaseModel, field_validator, ConfigDict, model_validator

from app.models.transaction import TransactionType
from app.schemas.validators import amount_validator, currency_code_validator
from decimal import Decimal


class TransactionTemplateCreate(BaseModel):
    name: str

    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return amount_validator(v)

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        return currency_code_validator(v)


class TransactionTemplateUpdate(TransactionTemplateCreate):
    pass


class TransactionTemplateResponse(BaseModel):
    id: int

    name: str

    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = None

    user_id: int

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UseTemplateRequest(BaseModel):
    type: TransactionType | None = None

    amount: Decimal | None = None

    currency_code: str | None = None

    category_id: int | None = None

    description: str | None = None

    date: date

    @field_validator("amount")
    @classmethod
    def validate_amount_if_provided(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return amount_validator(v)
        return v

    @field_validator("currency_code")
    @classmethod
    def validate_currency_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            return currency_code_validator(v)
        return v

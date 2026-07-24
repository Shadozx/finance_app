from pydantic import BaseModel, field_validator, ConfigDict, model_validator, Field
from datetime import date

from app.models.transaction import TransactionType
from app.schemas.validators import amount_validator, currency_code_validator, MAX_DESCRIPTION_LENGTH
from decimal import Decimal


class TransactionCreate(BaseModel):
    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    date: date

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return amount_validator(v)

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        return currency_code_validator(v)


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


class TransactionFilters(BaseModel):
    type: TransactionType | None = None

    currency_code: str | None = None

    start_date: date | None = None

    end_date: date | None = None

    category_id: int | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            return currency_code_validator(v)
        return v

    @model_validator(mode="after")
    def validate_dates(self) -> "TransactionFilters":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("Start date cannot be greater than end date")

        return self

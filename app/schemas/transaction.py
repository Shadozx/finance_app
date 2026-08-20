from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.transaction import TransactionKind, TransactionType
from app.schemas.validators import MAX_DESCRIPTION_LENGTH, amount_validator, currency_code_validator


class TransactionCreate(BaseModel):
    type: TransactionType

    amount: Decimal

    currency_code: str

    settled_amount: Decimal | None = None

    category_id: int | None = None

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    account_id: int

    date: date

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return amount_validator(v)

    @field_validator("settled_amount")
    @classmethod
    def validate_settled_amount_if_provided(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return amount_validator(v)
        return v

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

    kind: TransactionKind

    currency_code: str

    settled_amount: Decimal

    settled_currency_code: str

    category_id: int | None = None

    description: str | None = None

    date: date

    user_id: int

    account_id: int

    transfer_group_id: UUID | None = None

    counterpart_account_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class TransactionFilters(BaseModel):
    type: TransactionType | None = None

    currency_code: str | None = None

    start_date: date | None = None

    end_date: date | None = None

    category_id: int | None = None

    account_id: int | None = None

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

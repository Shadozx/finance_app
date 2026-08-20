from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from app.schemas.validators import MAX_DESCRIPTION_LENGTH, amount_validator


class TransferCreate(BaseModel):
    from_account_id: int

    to_account_id: int

    from_amount: Decimal

    to_amount: Decimal

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    date: date

    @field_validator("from_amount", "to_amount")
    @classmethod
    def validate_amounts(cls, v: Decimal) -> Decimal:
        amount = amount_validator(v)

        if amount == 0:
            raise ValueError("Transfer amount must be greater than zero")

        return amount

    @model_validator(mode="after")
    def validate_accounts_differ(self) -> "TransferCreate":
        if self.from_account_id == self.to_account_id:
            raise ValueError("Transfer must be between two different accounts")

        return self


class TransferUpdate(TransferCreate):
    pass


class TransferResponse(BaseModel):
    transfer_group_id: UUID

    from_account_id: int
    from_account_name: str
    from_currency_code: str
    from_amount: Decimal

    to_account_id: int
    to_account_name: str
    to_currency_code: str
    to_amount: Decimal

    exchange_rate: Decimal | None

    description: str | None = None

    date: date

    @field_serializer("from_amount", "to_amount")
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

    @field_serializer("exchange_rate")
    def serialize_exchange_rate(self, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None

        return value.quantize(Decimal("0.0001"))

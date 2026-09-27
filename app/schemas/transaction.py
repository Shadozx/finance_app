from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.models.enums import TransactionKind, TransactionType
from app.schemas.pagination import RecordPagination
from app.schemas.validators import (
    MAX_DESCRIPTION_LENGTH,
    amount_validator,
    currency_code_validator,
    validate_date_order,
    validate_end_date_against_start,
)


class TransactionSplitCreate(BaseModel):
    category_id: int | None = None
    amount: Decimal
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return amount_validator(v)


class TransactionSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    amount: Decimal
    settled_amount: Decimal
    description: str | None


class TransactionCreate(BaseModel):
    type: TransactionType

    amount: Decimal

    currency_code: str

    settled_amount: Decimal | None = None

    category_id: int | None = None

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    account_id: int

    date: date

    splits: list[TransactionSplitCreate] | None = Field(None, min_length=2, max_length=50)

    @model_validator(mode="after")
    def validate_splits(self):
        if self.splits is None:
            return self

        if self.category_id is not None:
            raise ValueError("Transaction with splits cannot have its own category")

        if self.amount == 0:
            raise ValueError("Transaction with zero amount cannot be split")

        total = sum(split.amount for split in self.splits)

        if total != self.amount:
            raise ValueError(f"Split amounts must add up to {self.amount}, got {total}")

        return self

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


class TransactionListItem(BaseModel):
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

    created_at: datetime

    updated_at: datetime

    account_id: int

    transfer_group_id: UUID | None = None

    counterpart_account_id: int | None = None

    has_splits: bool = False

    model_config = ConfigDict(from_attributes=True)


class TransactionResponse(TransactionListItem):
    splits: list[TransactionSplitResponse] | None = None


class TransactionFilters(RecordPagination):
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

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date | None, info: ValidationInfo) -> date | None:
        return validate_end_date_against_start(v, info, check_dates=validate_date_order)

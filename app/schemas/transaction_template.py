from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.transaction import TransactionType
from app.schemas.validators import (
    MAX_DESCRIPTION_LENGTH,
    amount_validator,
    currency_code_validator,
    name_validator,
)


class TransactionTemplateSplitCreate(BaseModel):
    category_id: int | None = None

    amount: Decimal

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return amount_validator(v)


class TransactionTemplateSplitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    category_id: int | None

    amount: Decimal

    description: str | None


class TransactionTemplateCreate(BaseModel):
    name: str

    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    splits: list[TransactionTemplateSplitCreate] | None = Field(None, min_length=2, max_length=50)

    @model_validator(mode="after")
    def validate_splits(self):
        if self.splits is None:
            return self

        if self.category_id is not None:
            raise ValueError("Transaction template with splits cannot have its own category")

        if self.amount == 0:
            raise ValueError("Transaction template with zero amount cannot be split")

        total = sum(split.amount for split in self.splits)

        if total != self.amount:
            raise ValueError(f"Split amounts must add up to {self.amount}, got {total}")

        return self

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return name_validator(v, "Template")

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


class TransactionTemplateListItem(BaseModel):
    id: int

    name: str

    amount: Decimal

    type: TransactionType

    currency_code: str

    category_id: int | None = None

    description: str | None = None

    user_id: int

    created_at: datetime

    has_splits: bool = False

    model_config = ConfigDict(from_attributes=True)


class TransactionTemplateResponse(TransactionTemplateListItem):
    splits: list[TransactionTemplateSplitResponse] | None = None


class UseTemplateRequest(BaseModel):
    type: TransactionType | None = None

    amount: Decimal | None = None

    currency_code: str | None = None

    settled_amount: Decimal | None = None

    category_id: int | None = None

    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)

    account_id: int

    date: date

    @field_validator("amount", "settled_amount")
    @classmethod
    def validate_amounts_if_provided(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            return amount_validator(v)
        return v

    @field_validator("currency_code")
    @classmethod
    def validate_currency_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            return currency_code_validator(v)
        return v

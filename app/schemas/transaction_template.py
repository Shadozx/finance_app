from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.core.error_codes import FieldErrorCode
from app.models.enums import TransactionType
from app.schemas.validators import (
    MAX_DESCRIPTION_LENGTH,
    amount_validator,
    currency_code_validator,
    field_error,
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
            raise field_error(
                FieldErrorCode.NOT_ALLOWED,
                "Transaction template with splits cannot have its own category",
            )

        if self.amount == 0:
            raise field_error(
                FieldErrorCode.NOT_ALLOWED, "Transaction template with zero amount cannot be split"
            )

        return self

    @field_validator("splits")
    @classmethod
    def validate_split_total(
        cls, v: list[TransactionTemplateSplitCreate] | None, info: ValidationInfo
    ) -> list[TransactionTemplateSplitCreate] | None:
        if v is None:
            return v

        amount = info.data.get("amount")
        # Let model rules report zero amounts or a category paired with splits first.
        if amount is None or amount == 0 or info.data.get("category_id") is not None:
            return v

        total = sum(split.amount for split in v)
        if total != amount:
            raise field_error(
                FieldErrorCode.MUST_MATCH,
                "Split amounts must add up to {amount}, got {total}",
                {"amount": amount, "total": total},
            )
        return v

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

    updated_at: datetime

    has_splits: bool = False

    model_config = ConfigDict(from_attributes=True)


class TransactionTemplateResponse(TransactionTemplateListItem):
    splits: list[TransactionTemplateSplitResponse] | None = None

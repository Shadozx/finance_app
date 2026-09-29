from datetime import date, datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from app.core.error_codes import FieldErrorCode
from app.schemas.pagination import RecordPagination
from app.schemas.validators import (
    amount_validator,
    currency_code_validator,
    field_error,
    validate_date_range,
    validate_end_date_against_start,
)


class BudgetCreate(BaseModel):
    name: str | None = None

    amount: Decimal

    currency_code: str

    category_id: int

    start_date: date

    end_date: date

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return v

        v = v.strip()

        if len(v) > 100:
            raise field_error(
                FieldErrorCode.STRING_TOO_LONG, "Budget name must be less than 100 characters"
            )

        return v or None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        return amount_validator(v)

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        return currency_code_validator(v)

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date, info: ValidationInfo) -> date:
        validate_end_date_against_start(v, info, check_dates=validate_date_range)
        return v


class BudgetUpdate(BudgetCreate):
    pass


class BudgetResponse(BaseModel):
    id: int

    name: str | None = None

    amount: Decimal

    currency_code: str

    category_id: int

    start_date: date

    end_date: date

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BudgetFilters(RecordPagination):
    currency_code: str | None = None

    category_id: int | None = None

    start_date: date | None = None

    end_date: date | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            return currency_code_validator(v)
        return v

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date | None, info: ValidationInfo) -> date | None:
        return validate_end_date_against_start(v, info, check_dates=validate_date_range)

    @model_validator(mode="after")
    def validate_dates(self) -> "BudgetFilters":
        if (self.start_date is None) != (self.end_date is None):
            raise field_error(
                FieldErrorCode.INCOMPLETE_RANGE, "Both dates must be provided, or neither"
            )

        return self


class BudgetStatusResponse(BaseModel):
    budget: BudgetResponse
    spent: Decimal
    remaining: Decimal
    percent: Decimal
    is_exceeded: bool

    @field_serializer("spent", "remaining", "percent")
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

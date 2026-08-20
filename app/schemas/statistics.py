import calendar
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, field_serializer, field_validator, model_validator

from app.models.transaction import TransactionType
from app.schemas.validators import currency_code_validator, validate_date_range


class StatisticsFilters(BaseModel):
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
    def validate_dates(self) -> "StatisticsFilters":
        if self.start_date is None and self.end_date is None:
            today = date.today()
            self.start_date = today.replace(day=1)
            last_day = calendar.monthrange(today.year, today.month)[1]
            self.end_date = date(today.year, today.month, last_day)

        if self.start_date is None or self.end_date is None:
            raise ValueError("Both dates must be provided, or neither")

        validate_date_range(self.start_date, self.end_date)

        return self


class CategoryStatisticsFilters(StatisticsFilters):
    type: TransactionType


class CurrencySummary(BaseModel):
    currency_code: str
    income: Decimal
    expense: Decimal
    net: Decimal

    @field_serializer("income", "expense", "net")
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class SummaryPeriod(BaseModel):
    start_date: date
    end_date: date


class SummaryResponse(BaseModel):
    period: SummaryPeriod
    currencies: list[CurrencySummary]


class CategoryAmount(BaseModel):
    category_id: int | None
    category_name: str | None
    total: Decimal

    @field_serializer("total")
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class CurrencyCategories(BaseModel):
    currency_code: str
    categories: list[CategoryAmount]


class CategorySummaryResponse(BaseModel):
    period: SummaryPeriod
    currencies: list[CurrencyCategories]

from datetime import datetime
from decimal import Decimal

from enum import Enum

from pydantic import BaseModel, field_validator, ConfigDict, field_serializer

from app.schemas.validators import name_validator, currency_code_validator


class AccountStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    ALL = "all"


class AccountCreate(BaseModel):
    name: str
    currency_code: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return name_validator(v, "Account")

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, v: str) -> str:
        return currency_code_validator(v)


class AccountUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return name_validator(v, "Account")


class AccountResponse(BaseModel):
    id: int
    name: str
    currency_code: str
    user_id: int
    created_at: datetime
    archived_at: datetime | None

    balance: Decimal

    @field_serializer("balance")
    def serialize_money(self, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, LiteralString, cast

from pydantic import ValidationInfo
from pydantic_core import PydanticCustomError

from app.core.error_codes import FieldErrorCode

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

MAX_DATE_RANGE_DAYS = 365

MAX_DESCRIPTION_LENGTH = 1024

MAX_NAME_LENGTH = 100


def field_error(
    code: FieldErrorCode,
    message: LiteralString,
    context: dict[str, Any] | None = None,
) -> PydanticCustomError:
    # Enum members are compile-time constants, which is what LiteralString protects
    return PydanticCustomError(cast(LiteralString, code.value), message, context)


def name_validator(name: str, entity: str) -> str:
    name = name.strip()

    if len(name) < 1:
        raise field_error(
            FieldErrorCode.STRING_TOO_SHORT,
            "{entity} name must be at least 1 character",
            {"entity": entity},
        )

    if len(name) > MAX_NAME_LENGTH:
        raise field_error(
            FieldErrorCode.STRING_TOO_LONG,
            "{entity} name must be less than {max_length} characters",
            {"entity": entity, "max_length": MAX_NAME_LENGTH},
        )

    return name


def password_validator(password: str) -> str:
    if len(password) < 8:
        raise field_error(FieldErrorCode.STRING_TOO_SHORT, "Password must be at least 8 characters")

    if not any(c.isdigit() for c in password):
        raise field_error(
            FieldErrorCode.PASSWORD_TOO_WEAK, "Password must contain at least one digit"
        )
    if not any(c.isalpha() for c in password):
        raise field_error(
            FieldErrorCode.PASSWORD_TOO_WEAK, "Password must contain at least one letter"
        )

    return password


def username_validator(username: str) -> str:
    username = username.strip()

    if len(username) < 3:
        raise field_error(FieldErrorCode.STRING_TOO_SHORT, "Username must be at least 3 characters")

    if len(username) > 50:
        raise field_error(
            FieldErrorCode.STRING_TOO_LONG, "Username must be less than 50 characters"
        )

    if not USERNAME_PATTERN.match(username):
        raise field_error(
            FieldErrorCode.STRING_PATTERN_MISMATCH,
            "Username can only contain letters, numbers and underscores",
        )

    return username


def amount_validator(amount: Decimal) -> Decimal:
    if not amount.is_finite():
        raise field_error(FieldErrorCode.FINITE_NUMBER, "Amount must be a finite number")

    if amount < 0:
        raise field_error(FieldErrorCode.GREATER_THAN_EQUAL, "Amount cannot be negative")

    if amount != amount.quantize(Decimal("0.01")):
        raise field_error(
            FieldErrorCode.DECIMAL_MAX_PLACES, "Amount cannot have more than 2 decimal places"
        )

    return amount


def currency_code_validator(currency_code: str) -> str:
    currency_code = currency_code.strip().upper()

    if len(currency_code) != 3:
        raise field_error(FieldErrorCode.INVALID_FORMAT, "Currency code must be 3 letters")

    return currency_code


def validate_date_order(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise field_error(
            FieldErrorCode.END_BEFORE_START, "Start date cannot be greater than end date"
        )


def validate_date_range(start_date: date, end_date: date) -> None:
    validate_date_order(start_date, end_date)
    if (end_date - start_date).days > MAX_DATE_RANGE_DAYS:
        raise field_error(
            FieldErrorCode.RANGE_TOO_LONG,
            "Date range cannot exceed 1 year — split into multiple requests",
        )


def validate_end_date_against_start(
    end_date: date | None,
    info: ValidationInfo,
    *,
    check_dates: Callable[[date, date], None],
) -> date | None:
    # start_date is absent from info.data if it failed its own validation
    start_date = info.data.get("start_date")
    if end_date is not None and start_date is not None:
        check_dates(start_date, end_date)
    return end_date

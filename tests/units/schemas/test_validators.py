from datetime import date
from decimal import Decimal

import pytest

from app.schemas.validators import (
    MAX_DATE_RANGE_DAYS,
    MAX_NAME_LENGTH,
    amount_validator,
    currency_code_validator,
    name_validator,
    password_validator,
    username_validator,
    validate_date_range,
)


class TestNameValidator:
    def test_name_returned_as_is(self):
        assert name_validator("Groceries", "Category") == "Groceries"

    def test_name_stripped(self):
        assert name_validator("  Groceries  ", "Category") == "Groceries"

    def test_name_at_max_length_allowed(self):
        name = "a" * MAX_NAME_LENGTH

        assert name_validator(name, "Category") == name

    def test_name_empty_rejected(self):
        with pytest.raises(ValueError, match="Category name must be at least 1 character"):
            name_validator("", "Category")

    def test_name_whitespace_only_rejected(self):
        """Stripping happens first, so a blank name is caught rather than stored."""
        with pytest.raises(ValueError, match="Category name must be at least 1 character"):
            name_validator("   ", "Category")

    def test_name_above_max_length_rejected(self):
        with pytest.raises(ValueError, match="must be less than"):
            name_validator("a" * (MAX_NAME_LENGTH + 1), "Category")

    def test_entity_name_appears_in_message(self):
        """One validator serves every entity: the message names the caller."""
        with pytest.raises(ValueError, match="Template name must be at least 1 character"):
            name_validator("", "Template")


class TestPasswordValidator:
    def test_valid_password_returned_as_is(self):
        assert password_validator("Password1") == "Password1"

    def test_password_not_stripped(self):
        """Unlike names, surrounding spaces are part of the secret."""
        assert password_validator("  Password1  ") == "  Password1  "

    def test_password_at_min_length_allowed(self):
        assert password_validator("passwor1") == "passwor1"

    def test_short_password_rejected(self):
        with pytest.raises(ValueError, match="Password must be at least 8 characters"):
            password_validator("Pass1")

    def test_password_without_digit_rejected(self):
        with pytest.raises(ValueError, match="Password must contain at least one digit"):
            password_validator("PasswordOnly")

    def test_password_without_letter_rejected(self):
        with pytest.raises(ValueError, match="Password must contain at least one letter"):
            password_validator("12345678")


class TestUsernameValidator:
    def test_valid_username_returned_as_is(self):
        assert username_validator("user_123") == "user_123"

    def test_username_stripped(self):
        assert username_validator("  user  ") == "user"

    def test_username_at_min_length_allowed(self):
        assert username_validator("abc") == "abc"

    def test_username_at_max_length_allowed(self):
        username = "a" * 50

        assert username_validator(username) == username

    def test_short_username_rejected(self):
        with pytest.raises(ValueError, match="Username must be at least 3 characters"):
            username_validator("ab")

    def test_long_username_rejected(self):
        with pytest.raises(ValueError, match="Username must be less than 50 characters"):
            username_validator("a" * 51)

    @pytest.mark.parametrize("username", ["user name", "user-name", "user.name", "üser", "user@x"])
    def test_username_with_disallowed_characters_rejected(self, username: str):
        with pytest.raises(ValueError, match="letters, numbers and underscores"):
            username_validator(username)


class TestAmountValidator:
    @pytest.mark.parametrize(
        "amount",
        [Decimal("0"), Decimal("0.01"), Decimal("0.1"), Decimal("150.00"), Decimal("99999.99")],
    )
    def test_valid_amount_returned_as_is(self, amount: Decimal):
        assert amount_validator(amount) == amount

    def test_zero_allowed(self):
        """A zero amount is a valid record, not a missing one."""
        assert amount_validator(Decimal("0.00")) == Decimal("0.00")

    def test_negative_amount_rejected(self):
        with pytest.raises(ValueError, match="Amount cannot be negative"):
            amount_validator(Decimal("-1.00"))

    @pytest.mark.parametrize("amount", [Decimal("33.333"), Decimal("0.001"), Decimal("1.0000")])
    def test_amount_with_more_than_two_decimals_rejected(self, amount: Decimal):
        """NUMERIC(15, 2) would silently round these, breaking split sums."""
        with pytest.raises(ValueError, match="more than 2 decimal places"):
            amount_validator(amount)

    @pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_amount_rejected(self, amount: str):
        """Comparing a non-finite exponent to an int raises TypeError, not ValueError."""
        with pytest.raises(ValueError, match="Amount must be a finite number"):
            amount_validator(Decimal(amount))


class TestCurrencyCodeValidator:
    def test_valid_code_returned_as_is(self):
        assert currency_code_validator("UAH") == "UAH"

    def test_code_uppercased(self):
        assert currency_code_validator("uah") == "UAH"

    def test_code_stripped(self):
        assert currency_code_validator("  usd  ") == "USD"

    @pytest.mark.parametrize("code", ["US", "USDT", ""])
    def test_code_of_wrong_length_rejected(self, code: str):
        with pytest.raises(ValueError, match="Currency code must be 3 letters"):
            currency_code_validator(code)


class TestValidateDateRange:
    def test_valid_range_passes(self):
        assert validate_date_range(date(2026, 1, 1), date(2026, 1, 31)) is None

    def test_same_day_allowed(self):
        assert validate_date_range(date(2026, 1, 1), date(2026, 1, 1)) is None

    def test_range_at_max_length_allowed(self):
        start = date(2026, 1, 1)

        assert validate_date_range(start, start.replace(year=2027)) is None

    def test_reversed_range_rejected(self):
        with pytest.raises(ValueError, match="Start date cannot be greater than end date"):
            validate_date_range(date(2026, 2, 1), date(2026, 1, 1))

    def test_range_above_max_length_rejected(self):
        start = date(2026, 1, 1)
        end = date(2027, 1, 2)

        assert (end - start).days == MAX_DATE_RANGE_DAYS + 1

        with pytest.raises(ValueError, match="Date range cannot exceed 1 year"):
            validate_date_range(start, end)

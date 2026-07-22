from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import BudgetCreate, BudgetFilters, BudgetStatusResponse, BudgetResponse


class TestBudgetCreate:
    def test_valid_full_input_passes(self):
        b = BudgetCreate(
            name="Food",
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.amount == Decimal("5000.00")
        assert b.currency_code == "USD"
        assert b.category_id == 1

    def test_name_is_optional(self):
        b = BudgetCreate(
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.name is None

    def test_name_at_max_length_passes(self):
        b = BudgetCreate(
            name="x" * 100,
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert len(b.name) == 100

    def test_name_too_long_raises(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                name="x" * 101,
                amount=Decimal("5000.00"),
                currency_code="USD",
                category_id=1,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )

    def test_name_explicit_none_passes(self):
        b = BudgetCreate(
            name=None,
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.name is None

    def test_name_empty_string_becomes_none(self):
        b = BudgetCreate(
            name="",
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.name is None

    def test_name_whitespace_becomes_none(self):
        b = BudgetCreate(
            name="   ",
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.name is None

    def test_name_is_stripped(self):
        b = BudgetCreate(
            name="  Food  ",
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.name == "Food"

    def test_zero_amount_is_allowed(self):
        b = BudgetCreate(
            amount=Decimal("0"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.amount == Decimal("0")

    def test_negative_amount_raises(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                amount=Decimal("-1.00"),
                currency_code="USD",
                category_id=1,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )

    def test_currency_code_normalized(self):
        b = BudgetCreate(
            amount=Decimal("5000.00"),
            currency_code="usd",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        assert b.currency_code == "USD"

    def test_currency_code_wrong_length_raises(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                amount=Decimal("5000.00"),
                currency_code="US",
                category_id=1,
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )

    def test_category_id_is_required(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                amount=Decimal("5000.00"),
                currency_code="USD",
                start_date=date(2026, 7, 1),
                end_date=date(2026, 7, 31),
            )

    def test_dates_are_required(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                amount=Decimal("5000.00"),
                currency_code="USD",
                category_id=1,
            )

    def test_start_after_end_raises(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                amount=Decimal("5000.00"),
                currency_code="USD",
                category_id=1,
                start_date=date(2026, 8, 1),
                end_date=date(2026, 7, 1),
            )

    def test_exactly_one_year_passes(self):
        b = BudgetCreate(
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert b.start_date == date(2024, 1, 1)

    def test_over_one_year_raises(self):
        with pytest.raises(ValidationError):
            BudgetCreate(
                amount=Decimal("5000.00"),
                currency_code="USD",
                category_id=1,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),
            )


class TestBudgetFilters:
    def test_empty_is_valid(self):
        f = BudgetFilters()
        assert f.start_date is None
        assert f.end_date is None

    def test_both_dates_provided_passes(self):
        f = BudgetFilters(start_date=date(2026, 7, 1), end_date=date(2026, 7, 31))
        assert f.start_date == date(2026, 7, 1)
        assert f.end_date == date(2026, 7, 31)

    def test_only_start_date_raises(self):
        with pytest.raises(ValidationError):
            BudgetFilters(start_date=date(2026, 7, 1))

    def test_only_end_date_raises(self):
        with pytest.raises(ValidationError):
            BudgetFilters(end_date=date(2026, 7, 31))

    def test_start_after_end_raises(self):
        with pytest.raises(ValidationError):
            BudgetFilters(start_date=date(2026, 8, 1), end_date=date(2026, 7, 1))

    def test_over_one_year_raises(self):
        with pytest.raises(ValidationError):
            BudgetFilters(start_date=date(2024, 1, 1), end_date=date(2025, 1, 1))

    def test_currency_code_normalized(self):
        f = BudgetFilters(currency_code="usd", start_date=date(2026, 7, 1), end_date=date(2026, 7, 31))
        assert f.currency_code == "USD"


class TestBudgetStatusResponse:
    def _budget(self) -> BudgetResponse:
        return BudgetResponse(
            id=1,
            name="Food",
            amount=Decimal("5000.00"),
            currency_code="USD",
            category_id=1,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )

    def test_money_fields_quantized_to_two_decimals(self):
        status = BudgetStatusResponse(
            budget=self._budget(),
            spent=Decimal("3333.333"),
            remaining=Decimal("1666.667"),
            percent=Decimal("66.6666666"),
            is_exceeded=False,
        )
        dumped = status.model_dump()
        assert dumped["spent"] == Decimal("3333.33")
        assert dumped["remaining"] == Decimal("1666.67")
        assert dumped["percent"] == Decimal("66.67")

    def test_exceeded_flag_and_negative_remaining(self):
        status = BudgetStatusResponse(
            budget=self._budget(),
            spent=Decimal("6000.00"),
            remaining=Decimal("-1000.00"),
            percent=Decimal("120.00"),
            is_exceeded=True,
        )
        assert status.is_exceeded is True
        assert status.remaining == Decimal("-1000.00")
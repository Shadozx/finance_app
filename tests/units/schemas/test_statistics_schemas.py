import calendar
import pytest
from datetime import date
from pydantic import ValidationError

from app.models import TransactionType
from app.schemas import StatisticsFilters, CategoryStatisticsFilters


class TestStatisticsFilters:
    def test_defaults_to_current_month(self):
        f = StatisticsFilters()
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        assert f.start_date == today.replace(day=1)
        assert f.end_date == date(today.year, today.month, last_day)

    def test_only_one_date_raises(self):
        with pytest.raises(ValidationError):
            StatisticsFilters(start_date=date(2026, 1, 1))

    def test_start_after_end_raises(self):
        with pytest.raises(ValidationError):
            StatisticsFilters(start_date=date(2026, 3, 1), end_date=date(2026, 1, 1))

    def test_exactly_one_year_passes(self):
        f = StatisticsFilters(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
        assert f.start_date == date(2024, 1, 1)

    def test_over_one_year_raises(self):
        with pytest.raises(ValidationError):
            StatisticsFilters(start_date=date(2024, 1, 1), end_date=date(2025, 1, 1))  # 366


class TestCategoryStatisticsFilters:
    def test_type_is_required(self):
        # No type provided at all -> must fail, because for a category
        # breakdown "income vs expense" is not optional.
        with pytest.raises(ValidationError):
            CategoryStatisticsFilters()

    def test_type_expense_is_accepted(self):
        f = CategoryStatisticsFilters(type=TransactionType.EXPENSE)
        assert f.type == TransactionType.EXPENSE

    def test_type_income_is_accepted(self):
        f = CategoryStatisticsFilters(type=TransactionType.INCOME)
        assert f.type == TransactionType.INCOME

    def test_inherited_date_default_still_works(self):
        # The date validator is inherited from StatisticsFilters:
        # with type present but no dates, it must default to the current month.
        f = CategoryStatisticsFilters(type=TransactionType.EXPENSE)

        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]

        assert f.start_date == today.replace(day=1)
        assert f.end_date == date(today.year, today.month, last_day)

    def test_inherited_range_over_one_year_fails(self):
        # The 1-year ceiling is inherited too.
        with pytest.raises(ValidationError):
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),  # 366 days
            )

    def test_inherited_only_one_date_fails(self):
        with pytest.raises(ValidationError):
            CategoryStatisticsFilters(
                type=TransactionType.EXPENSE,
                start_date=date(2026, 1, 1),
            )

    def test_valid_full_input_passes(self):
        f = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 7),
        )
        assert f.type == TransactionType.EXPENSE
        assert f.start_date == date(2026, 3, 1)
        assert f.end_date == date(2026, 3, 7)

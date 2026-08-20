import pytest
from decimal import Decimal
from datetime import date

from app.models import TransactionType
from app.repositories import TransactionRepository
from app.repositories.types import SummaryRow, CategorySummaryRow
from app.services import StatisticsService
from app.schemas import StatisticsFilters, CategoryStatisticsFilters


@pytest.fixture
def statistics_service(
    transaction_repo_mock: TransactionRepository,
):
    return StatisticsService(transaction_repo_mock)


class TestGetSummary:
    async def test_get_summary_success(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        transaction_repo_mock.get_summary.return_value = [
            SummaryRow("USD", TransactionType.INCOME, Decimal("10500.00")),
            SummaryRow("USD", TransactionType.EXPENSE, Decimal("50.00")),
            SummaryRow("UAH", TransactionType.EXPENSE, Decimal("350.00")),
        ]

        filters = StatisticsFilters(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))

        summary = await statistics_service.get_summary(user_id, filters)

        assert len(summary.currencies) == 2

        by_code = {c.currency_code: c for c in summary.currencies}

        assert by_code["UAH"].income == Decimal("0")
        assert by_code["UAH"].expense == Decimal("350.00")
        assert by_code["UAH"].net == Decimal("-350.00")

        assert by_code["USD"].income == Decimal("10500.00")
        assert by_code["USD"].expense == Decimal("50.00")
        assert by_code["USD"].net == Decimal("10450.00")

        assert [c.currency_code for c in summary.currencies] == ["UAH", "USD"]

        assert summary.period.start_date == filters.start_date
        assert summary.period.end_date == filters.end_date

        transaction_repo_mock.get_summary.assert_called_once_with(user_id, filters)

    async def test_get_summary_fills_missing_type(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        transaction_repo_mock.get_summary.return_value = [
            SummaryRow("UAH", TransactionType.EXPENSE, Decimal("350.00"))
        ]

        filters = StatisticsFilters()

        summary = await statistics_service.get_summary(user_id, filters)

        assert len(summary.currencies) == 1

        by_code = {c.currency_code: c for c in summary.currencies}

        assert by_code["UAH"].income == Decimal("0")
        assert by_code["UAH"].expense == Decimal("350.00")
        assert by_code["UAH"].net == Decimal("-350.00")

        transaction_repo_mock.get_summary.assert_called_once_with(user_id, filters)

    async def test_get_summary_sorted_by_currency(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        transaction_repo_mock.get_summary.return_value = [
            SummaryRow("USD", TransactionType.EXPENSE, Decimal("50.00")),
            SummaryRow("EUR", TransactionType.EXPENSE, Decimal("30.00")),
            SummaryRow("UAH", TransactionType.EXPENSE, Decimal("100.00")),
        ]

        filters = StatisticsFilters()

        summary = await statistics_service.get_summary(user_id, filters)

        assert len(summary.currencies) == 3

        by_code = {c.currency_code: c for c in summary.currencies}

        assert by_code["EUR"].expense == Decimal("30.00")

        assert [c.currency_code for c in summary.currencies] == ["EUR", "UAH", "USD"]

        transaction_repo_mock.get_summary.assert_called_once_with(user_id, filters)

    async def test_get_summary_empty(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        user_id = 1

        transaction_repo_mock.get_summary.return_value = []

        filters = StatisticsFilters()

        summary = await statistics_service.get_summary(user_id, filters)

        assert len(summary.currencies) == 0

        assert summary.period.start_date == filters.start_date
        assert summary.period.end_date == filters.end_date

        transaction_repo_mock.get_summary.assert_called_once_with(user_id, filters)


class TestGetByCategory:
    async def test_get_by_category_success(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        # Two currencies, several categories, one uncategorized row.
        transaction_repo_mock.get_by_category.return_value = [
            CategorySummaryRow("USD", 5, "Food", Decimal("200.00")),
            CategorySummaryRow("UAH", 5, "Food", Decimal("350.00")),
            CategorySummaryRow("UAH", None, None, Decimal("100.00")),
        ]

        filters = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        result = await statistics_service.get_by_category(1, filters)

        # Grouped into two currencies
        assert len(result.currencies) == 2

        by_currency = {c.currency_code: c for c in result.currencies}

        # USD has one category
        usd_cats = by_currency["USD"].categories
        assert len(usd_cats) == 1
        assert usd_cats[0].category_id == 5
        assert usd_cats[0].category_name == "Food"
        assert usd_cats[0].total == Decimal("200.00")

        # UAH has two categories (Food + uncategorized)
        uah_cats = by_currency["UAH"].categories
        assert len(uah_cats) == 2

        # Period is echoed
        assert result.period.start_date == filters.start_date
        assert result.period.end_date == filters.end_date

        transaction_repo_mock.get_by_category.assert_called_once_with(1, filters)

    async def test_get_by_category_currencies_sorted_by_code(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        # Deliberately reversed currency order in the input.
        transaction_repo_mock.get_by_category.return_value = [
            CategorySummaryRow("USD", 5, "Food", Decimal("50.00")),
            CategorySummaryRow("EUR", 5, "Food", Decimal("30.00")),
            CategorySummaryRow("UAH", 5, "Food", Decimal("100.00")),
        ]

        filters = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        result = await statistics_service.get_by_category(1, filters)

        codes = [c.currency_code for c in result.currencies]
        assert codes == ["EUR", "UAH", "USD"]

    async def test_get_by_category_categories_sorted_by_total_desc(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        # Same currency, categories in ascending order in the input;
        # output must be descending by total.
        transaction_repo_mock.get_by_category.return_value = [
            CategorySummaryRow("UAH", 1, "Small", Decimal("100.00")),
            CategorySummaryRow("UAH", 2, "Big", Decimal("500.00")),
            CategorySummaryRow("UAH", 3, "Medium", Decimal("300.00")),
        ]

        filters = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        result = await statistics_service.get_by_category(1, filters)

        cats = result.currencies[0].categories
        totals = [c.total for c in cats]
        assert totals == [Decimal("500.00"), Decimal("300.00"), Decimal("100.00")]

    async def test_get_by_category_equal_totals_tiebreak_by_name(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        # Two categories with the SAME total -> order must be deterministic,
        # broken by name alphabetically.
        transaction_repo_mock.get_by_category.return_value = [
            CategorySummaryRow("UAH", 1, "Transport", Decimal("200.00")),
            CategorySummaryRow("UAH", 2, "Food", Decimal("200.00")),
        ]

        filters = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        result = await statistics_service.get_by_category(1, filters)

        names = [c.category_name for c in result.currencies[0].categories]
        # Equal totals -> alphabetical: Food before Transport
        assert names == ["Food", "Transport"]

    async def test_get_by_category_uncategorized_does_not_break_sorting(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        # An uncategorized row (name=None) with the SAME total as a named one.
        # This is the case that would raise TypeError if None hit string comparison.
        transaction_repo_mock.get_by_category.return_value = [
            CategorySummaryRow("UAH", 1, "Food", Decimal("200.00")),
            CategorySummaryRow("UAH", None, None, Decimal("200.00")),
        ]

        filters = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        # Must not raise.
        result = await statistics_service.get_by_category(1, filters)

        cats = result.currencies[0].categories
        assert len(cats) == 2
        # "" (from None) sorts before "Food", so uncategorized comes first on tie.
        assert cats[0].category_name is None
        assert cats[1].category_name == "Food"

    async def test_get_by_category_empty(
        self,
        statistics_service: StatisticsService,
        transaction_repo_mock: TransactionRepository,
    ):
        transaction_repo_mock.get_by_category.return_value = []

        filters = CategoryStatisticsFilters(
            type=TransactionType.EXPENSE,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        result = await statistics_service.get_by_category(1, filters)

        assert result.currencies == []
        assert result.period.start_date == filters.start_date
        assert result.period.end_date == filters.end_date

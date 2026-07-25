from decimal import Decimal

from app.models import TransactionType
from app.repositories import TransactionRepository
from app.schemas import StatisticsFilters, CurrencySummary, SummaryPeriod, SummaryResponse, CategoryStatisticsFilters, \
    CategoryAmount, CurrencyCategories, CategorySummaryResponse


class StatisticsService:
    def __init__(self, transaction_repository: TransactionRepository):
        self.transaction_repository = transaction_repository

    async def get_summary(
            self,
            user_id: int,
            filters: StatisticsFilters
    ) -> SummaryResponse:
        rows = await self.transaction_repository.get_summary(user_id, filters)

        accumulator: dict[str, dict[str, Decimal]] = {}

        for row in rows:
            entry = accumulator.setdefault(
                row.currency_code,
                {"income": Decimal("0"), "expense": Decimal("0")},
            )
            if row.type == TransactionType.INCOME:
                entry["income"] = row.total
            else:
                entry["expense"] = row.total

        currencies = [
            CurrencySummary(
                currency_code=code,
                income=data["income"],
                expense=data["expense"],
                net=data["income"] - data["expense"],
            )
            for code, data in accumulator.items()
        ]

        currencies.sort(key=lambda c: c.currency_code)

        assert filters.start_date is not None
        assert filters.end_date is not None

        return SummaryResponse(
            period=SummaryPeriod(
                start_date=filters.start_date,
                end_date=filters.end_date,
            ),
            currencies=currencies,
        )

    async def get_by_category(
            self,
            user_id: int,
            filters: CategoryStatisticsFilters
    ) -> CategorySummaryResponse:
        rows = await self.transaction_repository.get_by_category(user_id, filters)

        accumulator: dict[str, list[CategoryAmount]] = {}

        for row in rows:
            entry = accumulator.setdefault(
                row.currency_code,
                []
            )

            entry.append(CategoryAmount(
                category_id=row.category_id,
                category_name=row.category_name,
                total=row.total,
            ))

        currencies = [
            CurrencyCategories(
                currency_code=code,
                categories=data,
            )

            for code, data in accumulator.items()
        ]

        currencies.sort(key=lambda c: c.currency_code)

        for currency in currencies:
            currency.categories.sort(key=lambda c: (-c.total, c.category_name or ""))

        assert filters.start_date is not None
        assert filters.end_date is not None

        return CategorySummaryResponse(
            period=SummaryPeriod(
                start_date=filters.start_date,
                end_date=filters.end_date,
            ),
            currencies=currencies,
        )

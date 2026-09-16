from app.core.exceptions import NotFoundException
from app.repositories import CurrencyRepository
from app.schemas import CurrencyResponse, Page


class CurrencyService:
    def __init__(self, currency_repository: CurrencyRepository):
        self.currency_repository = currency_repository

    async def get_active_currencies(
        self,
        limit: int = 200,
        offset: int = 0,
    ) -> Page[CurrencyResponse]:
        rows = await self.currency_repository.get_active(limit + 1, offset)

        has_more = len(rows) > limit
        active_currencies = rows[:limit]

        return Page(
            items=[CurrencyResponse.model_validate(currency) for currency in active_currencies],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    async def get_currency(self, code: str) -> CurrencyResponse:
        code = code.upper().strip()

        existing_currency = await self.currency_repository.get_by_code(code)

        if not existing_currency:
            raise NotFoundException("Currency not found")

        return CurrencyResponse.model_validate(existing_currency)

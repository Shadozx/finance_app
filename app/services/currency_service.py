from app.repositories import CurrencyRepository
from app.schemas import CurrencyResponse
from app.core.exceptions import NotFoundException


class CurrencyService:
    def __init__(self, currency_repository: CurrencyRepository):
        self.currency_repository = currency_repository

    async def get_active_currencies(self) -> list[CurrencyResponse]:
        active_currencies = await self.currency_repository.get_all_active()

        return [CurrencyResponse.model_validate(currency) for currency in active_currencies]

    async def get_currency(self, code: str) -> CurrencyResponse:
        code = code.upper().strip()

        existing_currency = await self.currency_repository.get_by_code(code)

        if not existing_currency:
            raise NotFoundException("Currency not found")

        return CurrencyResponse.model_validate(existing_currency)

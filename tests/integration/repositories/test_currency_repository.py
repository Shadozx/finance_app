from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency
from app.repositories import CurrencyRepository


class TestGetAllActive:
    async def test_get_all_active_returns_only_active(
        self,
        test_session: AsyncSession,
        currency_repository: CurrencyRepository,
        uah_currency: Currency,
    ):
        inactive_currency = Currency(
            code="EUR",
            symbol="€",
            name="Euro",
            is_active=False,
        )
        test_session.add(inactive_currency)
        await test_session.flush()

        currencies = await currency_repository.get_all_active()

        assert len(currencies) == 1
        assert currencies[0].code == uah_currency.code
        assert inactive_currency.code not in {currency.code for currency in currencies}

    async def test_get_all_active_ordered_by_code(
        self,
        test_session: AsyncSession,
        currency_repository: CurrencyRepository,
        uah_currency: Currency,
        usd_currency: Currency,
    ):
        eur_currency = Currency(
            code="EUR",
            symbol="€",
            name="Euro",
            is_active=True,
        )
        test_session.add(eur_currency)
        await test_session.flush()

        currencies = await currency_repository.get_all_active()

        assert [currency.code for currency in currencies] == [
            eur_currency.code,
            uah_currency.code,
            usd_currency.code,
        ]

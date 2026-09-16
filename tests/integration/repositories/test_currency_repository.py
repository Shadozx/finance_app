from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency
from app.repositories import CurrencyRepository


class TestGetActive:
    async def test_get_active_returns_only_active(
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

        currencies = await currency_repository.get_active()

        assert len(currencies) == 1
        assert currencies[0].code == uah_currency.code
        assert inactive_currency.code not in {currency.code for currency in currencies}

    async def test_get_active_ordered_by_code(
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

        currencies = await currency_repository.get_active()

        assert [currency.code for currency in currencies] == [
            eur_currency.code,
            uah_currency.code,
            usd_currency.code,
        ]

    async def test_get_active_pagination_does_not_repeat_or_skip(
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

        first_page_limit = 2
        second_page_limit = 1

        first_page = await currency_repository.get_active(limit=first_page_limit, offset=0)
        second_page = await currency_repository.get_active(
            limit=second_page_limit, offset=first_page_limit
        )

        returned_codes = [currency.code for currency in first_page + second_page]
        expected_codes = sorted([eur_currency.code, uah_currency.code, usd_currency.code])

        assert returned_codes == expected_codes

    async def test_get_active_pagination_limit(
        self,
        currency_repository: CurrencyRepository,
        uah_currency: Currency,
        usd_currency: Currency,
    ):
        limit = 1

        currencies = await currency_repository.get_active(limit=limit)

        assert len(currencies) == limit

    async def test_get_active_pagination_offset(
        self,
        currency_repository: CurrencyRepository,
        uah_currency: Currency,
        usd_currency: Currency,
    ):
        offset = 1

        currencies = await currency_repository.get_active(offset=offset)

        assert [currency.code for currency in currencies] == [usd_currency.code]

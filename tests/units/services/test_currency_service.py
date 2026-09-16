import pytest

from app.core.exceptions import NotFoundException
from app.models import Currency
from app.repositories import CurrencyRepository
from app.schemas import CurrencyResponse
from app.services import CurrencyService


class TestGetActiveCurrencies:
    async def test_active_currencies(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
    ):
        active_currencies = [
            Currency(code="UAH", symbol="₴", name="Ukrainian Hryvnia", is_active=True),
            Currency(code="USD", symbol="$", name="US Dollar", is_active=True),
            Currency(code="EUR", symbol="€", name="Euro", is_active=True),
        ]
        currency_repo_mock.get_active.return_value = active_currencies

        result = await currency_service.get_active_currencies()

        assert result.items == [CurrencyResponse.model_validate(c) for c in active_currencies]

        currency_repo_mock.get_active.assert_called_once()

    async def test_active_empty_currencies(
        self, currency_repo_mock: CurrencyRepository, currency_service: CurrencyService
    ):
        active_currencies = []
        currency_repo_mock.get_active.return_value = active_currencies

        actual = await currency_service.get_active_currencies()

        assert actual.items == [CurrencyResponse.model_validate(c) for c in active_currencies]

        currency_repo_mock.get_active.assert_called_once()

    async def test_get_active_currencies_reports_more_when_extra_row_returned(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
    ):
        limit = 2
        offset = 4

        rows = [
            Currency(code=f"C{index:02d}", symbol="¤", name=f"Currency {index}", is_active=True)
            for index in range(limit + 1)
        ]
        currency_repo_mock.get_active.return_value = rows

        result = await currency_service.get_active_currencies(limit, offset)

        assert result.has_more is True
        assert len(result.items) == limit

        currency_repo_mock.get_active.assert_called_once_with(limit + 1, offset)

    async def test_get_active_currencies_reports_no_more_on_last_page(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
    ):
        limit = 3

        rows = [
            Currency(code=f"C{index:02d}", symbol="¤", name=f"Currency {index}", is_active=True)
            for index in range(limit - 1)
        ]
        currency_repo_mock.get_active.return_value = rows

        result = await currency_service.get_active_currencies(limit, 0)

        assert result.has_more is False
        assert result.items == [CurrencyResponse.model_validate(row) for row in rows]

    async def test_get_active_currencies_reports_no_more_when_rows_match_limit(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
    ):
        limit = 2

        rows = [
            Currency(code=f"C{index:02d}", symbol="¤", name=f"Currency {index}", is_active=True)
            for index in range(limit)
        ]
        currency_repo_mock.get_active.return_value = rows

        result = await currency_service.get_active_currencies(limit, 0)

        assert result.has_more is False
        assert len(result.items) == limit


class TestGetCurrency:
    async def test_get_currency_success(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
        existing_currency: Currency,
    ):
        currency_repo_mock.get_by_code.return_value = existing_currency

        result = await currency_service.get_currency(existing_currency.code)

        assert result == CurrencyResponse.model_validate(existing_currency)

        currency_repo_mock.get_by_code.assert_called_once_with(existing_currency.code)

    async def test_get_currency_lower_case_currency_code(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
        existing_currency: Currency,
    ):
        lower_case_currency_code = "uah"

        currency_repo_mock.get_by_code.return_value = existing_currency

        result = await currency_service.get_currency(lower_case_currency_code)

        assert result == CurrencyResponse.model_validate(existing_currency)

        call_args = currency_repo_mock.get_by_code.call_args[0][0]

        assert call_args == existing_currency.code

    async def test_get_currency_currency_code_with_spaces(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
        existing_currency: Currency,
    ):
        currency_code_with_spaces = " UAH "

        currency_repo_mock.get_by_code.return_value = existing_currency

        result = await currency_service.get_currency(currency_code_with_spaces)

        assert result == CurrencyResponse.model_validate(existing_currency)

        call_args = currency_repo_mock.get_by_code.call_args[0][0]

        assert call_args == existing_currency.code

    async def test_get_currency_not_found(
        self,
        currency_service: CurrencyService,
        currency_repo_mock: CurrencyRepository,
    ):
        currency_repo_mock.get_by_code.return_value = None

        not_existing_currency = "UAH"

        with pytest.raises(NotFoundException, match="Currency not found"):
            await currency_service.get_currency(not_existing_currency)

        currency_repo_mock.get_by_code.assert_called_once_with(not_existing_currency)

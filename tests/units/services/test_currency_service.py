import pytest

from app.models import Currency
from app.services import CurrencyService
from app.repositories import CurrencyRepository
from app.schemas import CurrencyResponse
from app.core.exceptions import NotFoundException


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
        currency_repo_mock.get_all_active.return_value = active_currencies

        result = await currency_service.get_active_currencies()

        assert result == [CurrencyResponse.model_validate(c) for c in active_currencies]

        currency_repo_mock.get_all_active.assert_called_once()

    async def test_active_empty_currencies(
        self, currency_repo_mock: CurrencyRepository, currency_service: CurrencyService
    ):
        active_currencies = []
        currency_repo_mock.get_all_active.return_value = active_currencies

        actual = await currency_service.get_active_currencies()

        assert actual == [CurrencyResponse.model_validate(c) for c in active_currencies]

        currency_repo_mock.get_all_active.assert_called_once()


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

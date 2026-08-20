from httpx import AsyncClient
from fastapi import status

from tests.integration.endpoints.types import CurrencyData

API_GET_CURRENCIES = "/api/v1/currencies"


class TestGetCurrencies:
    async def test_get_currencies_empty_success_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.get(API_GET_CURRENCIES)

        assert response.status_code == status.HTTP_200_OK

        assert response.json() == []

    async def test_get_currencies_returns_only_active(
        self,
        client: AsyncClient,
        active_currency: CurrencyData,
        inactive_currency: CurrencyData,
    ):
        response = await client.get(API_GET_CURRENCIES)

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        codes = {currency["code"] for currency in body}

        assert active_currency["code"] in codes
        assert inactive_currency["code"] not in codes
        assert all(currency["is_active"] is True for currency in body)


class TestGetCurrencyByCode:
    async def test_get_currency_by_code_success(
        self,
        client: AsyncClient,
        active_currency: CurrencyData,
    ):
        response = await client.get(f"{API_GET_CURRENCIES}/{active_currency['code']}")

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["code"] == active_currency["code"]
        assert body["name"] == active_currency["name"]
        assert body["symbol"] == active_currency["symbol"]
        assert body["is_active"] == active_currency["is_active"]

    async def test_get_currency_by_code_lowercase_normalized(
        self,
        client: AsyncClient,
        active_currency: CurrencyData,
    ):
        response = await client.get(f"{API_GET_CURRENCIES}/{active_currency['code'].lower()}")

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["code"] == active_currency["code"]
        assert body["name"] == active_currency["name"]
        assert body["symbol"] == active_currency["symbol"]
        assert body["is_active"] == active_currency["is_active"]

    async def test_get_currency_by_code_unknown(
        self,
        client: AsyncClient,
    ):
        response = await client.get(f"{API_GET_CURRENCIES}/XXX")

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_get_currency_by_code_returns_inactive_currency(
        self,
        client: AsyncClient,
        inactive_currency: CurrencyData,
    ):
        response = await client.get(f"{API_GET_CURRENCIES}/{inactive_currency['code']}")

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["code"] == inactive_currency["code"]
        assert body["name"] == inactive_currency["name"]
        assert body["symbol"] == inactive_currency["symbol"]
        assert body["is_active"] == inactive_currency["is_active"]

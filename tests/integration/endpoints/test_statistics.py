import calendar
from datetime import date

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency
from tests.integration.endpoints.helpers import (
    account_payload,
    category_payload,
    create_account,
    create_category,
    create_transaction,
    transaction_payload,
)
from tests.integration.endpoints.types import (
    AccountData,
    AuthenticatedUser,
    CurrencyData,
)

API_SUMMARY = "/api/v1/statistics/summary"

API_CATEGORIES = "/api/v1/statistics/categories"


@pytest.fixture
async def second_account(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    second_currency: CurrencyData,
) -> AccountData:
    return await create_account(
        client,
        account_payload(name="UAH Account", currency_code=second_currency["code"]),
        authenticated_user["headers"],
    )


def summaries_by_code(body: dict) -> dict[str, dict]:
    """Index the currencies list by currency_code for order-independent lookup."""
    return {c["currency_code"]: c for c in body["currencies"]}


class TestGetSummary:
    async def test_get_summary_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        second_account: AccountData,
        active_currency: CurrencyData,
        second_currency: CurrencyData,
    ):
        # USD: income 10000 + 500 = 10500, expense 50
        await create_transaction(
            client,
            transaction_payload(
                date="2026-01-15",
                amount="10000.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-03-01",
                amount="500.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="50.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        # UAH: expense 350 (no income at all)
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="350.00",
                transaction_type="EXPENSE",
                currency_code=second_currency["code"],
                account_id=second_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        # period echoes the applied range
        assert body["period"]["start_date"] == "2026-01-01"
        assert body["period"]["end_date"] == "2026-03-31"

        assert len(body["currencies"]) == 2

        by_code = summaries_by_code(body)

        # Amounts come back as strings (Decimal serialization)
        assert by_code["USD"]["income"] == "10500.00"
        assert by_code["USD"]["expense"] == "50.00"
        assert by_code["USD"]["net"] == "10450.00"

        assert by_code["UAH"]["income"] == "0.00"
        assert by_code["UAH"]["expense"] == "350.00"
        assert by_code["UAH"]["net"] == "-350.00"

    async def test_get_summary_sorted_by_currency(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        second_account: AccountData,
        active_currency: CurrencyData,
        second_currency: CurrencyData,
    ):
        # Create UAH first, USD second — response must still be alphabetical.
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="350.00",
                transaction_type="EXPENSE",
                currency_code=second_currency["code"],  # UAH
                account_id=second_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-11",
                amount="50.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],  # USD
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        codes = [c["currency_code"] for c in body["currencies"]]

        assert codes == ["UAH", "USD"]

    async def test_get_summary_uses_settled_currency(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        second_account: AccountData,
        active_currency: CurrencyData,
        second_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="24.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                settled_amount="1050.00",
                account_id=second_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body["currencies"]) == 1

        by_code = summaries_by_code(body)

        assert by_code[second_currency["code"]]["expense"] == "1050.00"
        assert by_code[second_currency["code"]]["net"] == "-1050.00"

    async def test_get_summary_fills_missing_type_with_zero(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        # Only an expense — income must still be present as "0.00".
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="350.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        by_code = summaries_by_code(body)

        assert by_code["USD"]["income"] == "0.00"
        assert by_code["USD"]["expense"] == "350.00"
        assert by_code["USD"]["net"] == "-350.00"

    async def test_get_summary_returns_only_own(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        # Our expense: 350 USD
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="350.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        other_account = await create_account(
            client,
            account_payload(currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        # Other user's expense in the SAME currency+type — must NOT leak into our sum.
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-20",
                amount="999.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=other_account["id"],
            ),
            other_authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        by_code = summaries_by_code(body)

        # 350, not 1349 — the other user's 999 did not bleed in.
        assert by_code["USD"]["expense"] == "350.00"
        assert by_code["USD"]["net"] == "-350.00"

    async def test_get_summary_empty(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["currencies"] == []
        assert body["period"]["start_date"] == "2026-01-01"
        assert body["period"]["end_date"] == "2026-03-31"

    async def test_get_summary_default_period_is_current_month(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        # No dates supplied — server should default to the current month.
        response = await client.get(
            API_SUMMARY,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        expected_start = today.replace(day=1).isoformat()
        expected_end = date(today.year, today.month, last_day).isoformat()

        assert body["period"]["start_date"] == expected_start
        assert body["period"]["end_date"] == expected_end

    async def test_get_summary_range_over_one_year_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2024-01-01", "end_date": "2025-01-01"},  # 366 days
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_summary_exactly_one_year_passes(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2024-01-01", "end_date": "2024-12-31"},  # 365 days
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_get_summary_only_start_date_provided_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-01-01"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_summary_start_date_after_end_date_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-03-01", "end_date": "2026-01-01"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_summary_filter_by_currency(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        second_account: AccountData,
        active_currency: CurrencyData,
        second_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="50.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],  # USD
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-11",
                amount="350.00",
                transaction_type="EXPENSE",
                currency_code=second_currency["code"],  # UAH
                account_id=second_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
                "currency_code": active_currency["code"],
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        # Only USD should remain after filtering.
        assert len(body["currencies"]) == 1
        assert body["currencies"][0]["currency_code"] == "USD"

    async def test_get_summary_filter_by_date_range(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        # In range
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="100.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        # Out of range (later)
        await create_transaction(
            client,
            transaction_payload(
                date="2026-05-15",
                amount="999.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_SUMMARY,
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        by_code = summaries_by_code(body)

        # Only the in-range 100 counts, not the 999 from May.
        assert by_code["USD"]["expense"] == "100.00"

    async def test_get_summary_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.get(API_SUMMARY)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


def categories_of(body: dict, currency_code: str) -> list[dict]:
    """Pull the categories list for a given currency out of the response."""
    for c in body["currencies"]:
        if c["currency_code"] == currency_code:
            return c["categories"]
    return []


class TestGetCategories:
    async def test_get_categories_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        category = await create_category(
            client,
            category_payload(name="Food"),
            authenticated_user["headers"],
        )

        # Two expenses in the same category (should sum to 350),
        # one expense with no category (500).
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="150.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="200.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-03-01",
                amount="500.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=None,
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_CATEGORIES,
            params={
                "type": "EXPENSE",
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["period"]["start_date"] == "2026-01-01"
        assert body["period"]["end_date"] == "2026-03-31"

        cats = categories_of(body, active_currency["code"])
        by_name = {c["category_name"]: c for c in cats}

        # Amounts come back as strings (Decimal serialization)
        assert by_name["Food"]["total"] == "350.00"
        assert by_name["Food"]["category_id"] == category["id"]

        # Uncategorized group present with null id/name
        assert None in by_name
        assert by_name[None]["total"] == "500.00"
        assert by_name[None]["category_id"] is None

    async def test_get_categories_requires_type(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        # No `type` param -> 422, because a category breakdown without
        # income/expense selection is meaningless.
        response = await client.get(
            API_CATEGORIES,
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_categories_sorted_by_total_desc(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        big = await create_category(
            client, category_payload(name="Big"), authenticated_user["headers"]
        )
        small = await create_category(
            client, category_payload(name="Small"), authenticated_user["headers"]
        )

        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="100.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=small["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-11",
                amount="900.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=big["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_CATEGORIES,
            params={"type": "EXPENSE", "start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        cats = categories_of(response.json(), active_currency["code"])
        names = [c["category_name"] for c in cats]

        # Largest total first
        assert names == ["Big", "Small"]

    async def test_get_categories_uncategorized_has_null_fields(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="120.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=None,
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_CATEGORIES,
            params={"type": "EXPENSE", "start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        cats = categories_of(response.json(), active_currency["code"])
        assert len(cats) == 1
        assert cats[0]["category_id"] is None
        assert cats[0]["category_name"] is None
        assert cats[0]["total"] == "120.00"

    async def test_get_categories_does_not_mix_types(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        category = await create_category(
            client,
            category_payload(name="Mixed"),
            authenticated_user["headers"],
        )

        # Same category: an income and an expense.
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="1000.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                category_id=category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-11",
                amount="300.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_CATEGORIES,
            params={"type": "EXPENSE", "start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        cats = categories_of(response.json(), active_currency["code"])
        by_name = {c["category_name"]: c for c in cats}

        # Only the expense counts: 300, NOT 1300.
        assert by_name["Mixed"]["total"] == "300.00"

    async def test_get_categories_returns_only_own(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        my_category = await create_category(
            client,
            category_payload(name="Mine"),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-10",
                amount="100.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=my_category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        other_account = await create_account(
            client,
            account_payload(currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        # Other user's expense in same currency, no category.
        await create_transaction(
            client,
            transaction_payload(
                date="2026-02-11",
                amount="999.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=None,
                account_id=other_account["id"],
            ),
            other_authenticated_user["headers"],
        )

        response = await client.get(
            API_CATEGORIES,
            params={"type": "EXPENSE", "start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        cats = categories_of(response.json(), active_currency["code"])
        # Only my one category, other user's 999 did not leak in.
        assert len(cats) == 1
        assert cats[0]["category_name"] == "Mine"
        assert cats[0]["total"] == "100.00"

    async def test_get_categories_empty(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_CATEGORIES,
            params={"type": "EXPENSE", "start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["currencies"] == []
        assert body["period"]["start_date"] == "2026-01-01"

    async def test_get_categories_range_over_one_year_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_CATEGORIES,
            params={
                "type": "EXPENSE",
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",  # 366 days
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_categories_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.get(
            API_CATEGORIES,
            params={"type": "EXPENSE"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

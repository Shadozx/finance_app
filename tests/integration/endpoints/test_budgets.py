import pytest
from httpx import AsyncClient
from fastapi import status

from tests.integration.endpoints.helpers import (
    create_category,
    category_payload,
)
from tests.integration.endpoints.types import (
    AuthenticatedUser,
    CurrencyData,
    CategoryData,
)

API_BUDGETS = "/api/v1/budgets"


def budget_payload(
        amount: str = "5000.00",
        currency_code: str = "USD",
        category_id: int | None = None,
        start_date: str = "2026-07-01",
        end_date: str = "2026-07-31",
        name: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "amount": amount,
        "currency_code": currency_code,
        "start_date": start_date,
        "end_date": end_date,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    if name is not None:
        payload["name"] = name
    return payload


@pytest.fixture
async def created_budget(
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
        created_category: CategoryData,
) -> dict:
    payload = budget_payload(
        currency_code=active_currency["code"],
        category_id=created_category["id"],
    )
    response = await client.post(
        API_BUDGETS,
        json=payload,
        headers=authenticated_user["headers"],
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


class TestCreateBudget:
    async def test_create_budget_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            name="Food budget",
        )

        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["id"] is not None
        assert body["amount"] == payload["amount"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["category_id"] == payload["category_id"]
        assert body["start_date"] == payload["start_date"]
        assert body["end_date"] == payload["end_date"]
        assert body["name"] == payload["name"]

    async def test_create_budget_without_name_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["name"] is None

    async def test_create_budget_zero_amount_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            amount="0.00",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["amount"] == "0.00"

    async def test_create_budget_duplicate_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_budget_other_user_category_forbidden(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            other_authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        other_category = await create_category(
            client,
            category_payload(name="Other cat"),
            other_authenticated_user["headers"],
        )
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=other_category["id"],
        )
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_create_budget_archived_category_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_category: CategoryData,
            active_currency: CurrencyData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=archived_category["id"],
        )
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_create_budget_inactive_currency_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            inactive_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=inactive_currency["code"],
            category_id=created_category["id"],
        )
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.parametrize("payload_update, reason", [
        ({"amount": "-1.00"}, "negative_amount"),
        ({"amount": None}, "amount_null"),
        ({"currency_code": "US"}, "currency_too_short"),
        ({"currency_code": "USDD"}, "currency_too_long"),
        ({"start_date": "not-a-date"}, "invalid_start"),
        ({"start_date": "2026-08-01"}, "start_after_end"),
        ({"category_id": None}, "category_required"),
    ])
    async def test_create_budget_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
            payload_update: dict,
            reason: str,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )
        payload.update(payload_update)
        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

    async def test_create_budget_without_token(
            self,
            client: AsyncClient,
            active_currency: CurrencyData,
    ):
        response = await client.post(API_BUDGETS, json=budget_payload())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetBudgets:
    async def test_get_budgets_default_active(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        await client.post(
            API_BUDGETS,
            json=budget_payload(
                currency_code=active_currency["code"],
                category_id=created_category["id"],
                start_date="2026-01-01",
                end_date="2026-12-31",
            ),
            headers=authenticated_user["headers"],
        )
        response = await client.get(API_BUDGETS, headers=authenticated_user["headers"])
        assert response.status_code == status.HTTP_200_OK

    async def test_get_budgets_returns_only_own(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            other_authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.get(
            API_BUDGETS,
            params={"start_date": "2026-07-01", "end_date": "2026-07-31"},
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_200_OK
        ids = {b["id"] for b in response.json()}
        assert created_budget["id"] in ids

        other_response = await client.get(
            API_BUDGETS,
            params={"start_date": "2026-07-01", "end_date": "2026-07-31"},
            headers=other_authenticated_user["headers"],
        )
        other_ids = {b["id"] for b in other_response.json()}
        assert created_budget["id"] not in other_ids

    async def test_get_budgets_single_date_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_BUDGETS,
            params={"start_date": "2026-07-01"},
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_get_budgets_without_token(self, client: AsyncClient):
        response = await client.get(API_BUDGETS)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetBudgetById:
    async def test_get_budget_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["id"] == created_budget["id"]

    async def test_get_budget_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_BUDGETS}/999", headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_budget_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}",
            headers=other_authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_budget_without_token(
            self,
            client: AsyncClient,
            created_budget: dict,
    ):
        response = await client.get(f"{API_BUDGETS}/{created_budget['id']}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetBudgetStatus:
    async def test_budget_status_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}/status",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert "spent" in body
        assert "remaining" in body
        assert "percent" in body
        assert "is_exceeded" in body
        assert "budget" in body
        assert body["is_exceeded"] is False

    async def test_budget_status_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_BUDGETS}/999/status", headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_budget_status_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}/status",
            headers=other_authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_budget_status_without_token(
            self,
            client: AsyncClient,
            created_budget: dict,
    ):
        response = await client.get(f"{API_BUDGETS}/{created_budget['id']}/status")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestUpdateBudget:
    async def test_update_budget_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            amount="8000.00",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            name="Updated",
        )
        response = await client.put(
            f"{API_BUDGETS}/{created_budget['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["amount"] == "8000.00"
        assert body["name"] == "Updated"

    async def test_update_budget_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )
        response = await client.put(
            f"{API_BUDGETS}/999", json=payload, headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_budget_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
    ):
        payload = budget_payload(currency_code=active_currency["code"], category_id=1)
        response = await client.put(
            f"{API_BUDGETS}/{created_budget['id']}",
            json=payload,
            headers=other_authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_update_budget_without_token(
            self,
            client: AsyncClient,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )

        response = await client.put(
            f"{API_BUDGETS}/{created_budget['id']}",
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestDeleteBudget:
    async def test_delete_budget_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.delete(
            f"{API_BUDGETS}/{created_budget['id']}",
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

        get_response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}",
            headers=authenticated_user["headers"],
        )
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_budget_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_BUDGETS}/999", headers=authenticated_user["headers"]
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_budget_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_budget: dict,
    ):
        response = await client.delete(
            f"{API_BUDGETS}/{created_budget['id']}",
            headers=other_authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_delete_budget_without_token(
            self,
            client: AsyncClient,
            created_budget: dict,
    ):
        response = await client.delete(f"{API_BUDGETS}/{created_budget['id']}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestBudgetEdgeCases:
    async def test_create_budget_name_too_long_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            name="x" * 101,
        )

        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_create_budget_name_at_max_length_passes(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            name="x" * 100,
        )

        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_201_CREATED

    async def test_create_single_day_budget_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            start_date="2026-07-15",
            end_date="2026-07-15",
        )

        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["start_date"] == body["end_date"]

    async def test_duplicate_with_different_name_still_conflicts(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        payload = budget_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            name="Completely different name",
        )

        response = await client.post(
            API_BUDGETS, json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_update_into_conflict_with_existing_budget(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        august = await client.post(
            API_BUDGETS,
            json=budget_payload(
                currency_code=active_currency["code"],
                category_id=created_category["id"],
                start_date="2026-08-01",
                end_date="2026-08-31",
            ),
            headers=authenticated_user["headers"],
        )
        assert august.status_code == status.HTTP_201_CREATED
        august_id = august.json()["id"]

        response = await client.put(
            f"{API_BUDGETS}/{august_id}",
            json=budget_payload(
                currency_code=active_currency["code"],
                category_id=created_category["id"],
                start_date="2026-07-01",
                end_date="2026-07-31",
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    async def test_update_same_budget_no_self_conflict(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        response = await client.put(
            f"{API_BUDGETS}/{created_budget['id']}",
            json=budget_payload(
                amount="9999.00",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["amount"] == "9999.00"

    @pytest.mark.parametrize("path_suffix", ["", "/status"])
    async def test_invalid_budget_id_returns_422(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            path_suffix: str,
    ):
        response = await client.get(
            f"{API_BUDGETS}/abc{path_suffix}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_update_invalid_id_returns_422(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        response = await client.put(
            f"{API_BUDGETS}/abc",
            json=budget_payload(
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_delete_invalid_id_returns_422(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_BUDGETS}/abc", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestBudgetStatusWithRealTransactions:
    async def test_status_counts_only_matching_transactions(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        from tests.integration.endpoints.helpers import create_transaction, transaction_payload

        await create_transaction(
            client,
            transaction_payload(
                date="2026-07-10",
                amount="2000.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                date="2026-07-12",
                amount="9999.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                date="2026-08-05",
                amount="888.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                date="2026-07-15",
                amount="777.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}/status",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert body["spent"] == "2000.00"
        assert body["remaining"] == "3000.00"
        assert body["percent"] == "40.00"
        assert body["is_exceeded"] is False

    async def test_status_exceeded_with_real_transactions(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_budget: dict,
            active_currency: CurrencyData,
            created_category: CategoryData,
    ):
        from tests.integration.endpoints.helpers import create_transaction, transaction_payload

        await create_transaction(
            client,
            transaction_payload(
                date="2026-07-10",
                amount="6000.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            f"{API_BUDGETS}/{created_budget['id']}/status",
            headers=authenticated_user["headers"],
        )

        body = response.json()

        assert body["spent"] == "6000.00"
        assert body["remaining"] == "-1000.00"
        assert body["percent"] == "120.00"
        assert body["is_exceeded"] is True

import pytest
from fastapi import status
from httpx import AsyncClient

from tests.integration.endpoints.helpers import (
    account_payload,
    archive_category,
    category_payload,
    create_account,
    create_category,
    create_transaction,
    split_payload,
    transaction_payload,
)
from tests.integration.endpoints.types import (
    AccountData,
    AuthenticatedUser,
    CategoryData,
    CurrencyData,
    TransactionData,
    TransferData,
)

API_TRANSACTIONS = "/api/v1/transactions"


@pytest.fixture
async def second_category(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
) -> CategoryData:
    return await create_category(
        client,
        category_payload(name="Household"),
        authenticated_user["headers"],
    )


@pytest.fixture
async def created_transaction(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    created_account: AccountData,
    active_currency: CurrencyData,
) -> TransactionData:
    payload = transaction_payload(
        currency_code=active_currency["code"], account_id=created_account["id"]
    )

    return await create_transaction(
        client,
        payload,
        authenticated_user["headers"],
    )


@pytest.fixture
async def created_split_transaction(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    created_account: AccountData,
    created_category: CategoryData,
    second_category: CategoryData,
    active_currency: CurrencyData,
) -> TransactionData:
    """A 1000.00 receipt split into 800.00 groceries and 200.00 household."""
    payload = transaction_payload(
        amount="1000.00",
        currency_code=active_currency["code"],
        category_id=None,
        description="ATB",
        account_id=created_account["id"],
        splits=[
            split_payload(created_category["id"], "800.00", "Groceries"),
            split_payload(second_category["id"], "200.00", "Household"),
        ],
    )

    return await create_transaction(client, payload, authenticated_user["headers"])


def sides_by_account(body: list[dict]) -> dict[int, dict]:
    """Index registry rows by account_id — a transfer has one row per account."""
    return {row["account_id"]: row for row in body}


class TestCreateTransaction:
    async def test_create_transaction_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            description="Lunch",
            account_id=created_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["date"] == payload["date"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert body["kind"] == "REGULAR"
        assert body["currency_code"] == payload["currency_code"]
        assert body["category_id"] == payload["category_id"]
        assert body["description"] == payload["description"]
        assert body["account_id"] == created_account["id"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_without_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"], account_id=created_account["id"]
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["date"] == payload["date"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["category_id"] is None
        assert body["description"] == payload["description"]
        assert body["account_id"] == created_account["id"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_zero_amount_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="0.00", currency_code=active_currency["code"], account_id=created_account["id"]
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["amount"] == payload["amount"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_description_at_max_length_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            description="x" * 1024,
            account_id=created_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["description"] == payload["description"]
        assert body["account_id"] == created_account["id"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_different_currency_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        uah_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="24.00",
            currency_code=active_currency["code"],
            settled_amount="1050.00",
            account_id=uah_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["description"] == payload["description"]
        assert body["account_id"] == uah_account["id"]

        assert body["amount"] == payload["amount"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["settled_amount"] == payload["settled_amount"]
        assert body["settled_currency_code"] == uah_account["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_redundant_settled_amount_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        uah_account: AccountData,
    ):
        payload = transaction_payload(
            amount="24.00",
            currency_code=uah_account["currency_code"],
            settled_amount="1050.00",
            account_id=uah_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transaction_with_other_user_category_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        other_category = await create_category(
            client,
            category_payload(
                name="Other user category",
            ),
            other_authenticated_user["headers"],
        )

        payload = transaction_payload(
            currency_code=active_currency["code"],
            category_id=other_category["id"],
            account_id=created_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_create_transaction_with_archived_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        archived_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            category_id=archived_category["id"],
            account_id=created_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transaction_with_unknown_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"], category_id=999, account_id=created_account["id"]
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_create_transaction_with_inactive_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        inactive_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=inactive_currency["code"], account_id=created_account["id"]
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transaction_with_unknown_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
    ):
        payload = transaction_payload(currency_code="XXX", account_id=created_account["id"])

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_create_transaction_currency_code_normalized(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"].lower(), account_id=created_account["id"]
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["currency_code"] == active_currency["code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_with_other_user_account_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        other_account = await create_account(
            client,
            account_payload(currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=other_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_create_transaction_with_unknown_account_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=999,
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_create_transaction_with_archived_account_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        archived_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=archived_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transaction_different_currency_without_settled_amount(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        second_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=second_currency["code"],
            account_id=created_account["id"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "payload_update, reason",
        [
            ({"date": "not-a-date"}, "invalid_date_format"),
            ({"date": None}, "date_null"),
            ({"amount": "-1.00"}, "negative_amount"),
            ({"amount": None}, "amount_null"),
            ({"type": None}, "type_null"),
            ({"type": "wrong"}, "invalid_type"),
            ({"currency_code": None}, "currency_code_null"),
            ({"currency_code": "US"}, "currency_code_too_short"),
            ({"currency_code": "USDD"}, "currency_code_too_long"),
            ({"description": "x" * 1025}, "description_too_long"),
            ({"account_id": None}, "account_id_null"),
            ({"account_id": "abc"}, "account_id_not_int"),
            ({"settled_amount": "-1.00"}, "negative_settled_amount"),
        ],
    )
    async def test_create_transaction_validation_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
        payload_update: dict[str, object],
        reason: str,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"], account_id=created_account["id"]
        )

        payload.update(payload_update)

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "missing_field",
        [
            "date",
            "amount",
            "type",
            "currency_code",
            "account_id",
        ],
    )
    async def test_create_transaction_required_fields_missing(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
        missing_field: str,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"], account_id=created_account["id"]
        )

        payload.pop(missing_field)

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, missing_field
        assert "detail" in response.json()

    async def test_create_transaction_with_splits_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            description="ATB",
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00", "Groceries"),
                split_payload(second_category["id"], "200.00", "Household"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["amount"] == payload["amount"]
        assert body["category_id"] is None
        assert body["has_splits"] is True
        assert body["account_id"] == created_account["id"]
        assert body["user_id"] == authenticated_user["user"]["id"]

        assert len(body["splits"]) == 2

        assert body["splits"][0]["id"] is not None
        assert body["splits"][0]["category_id"] == created_category["id"]
        assert body["splits"][0]["amount"] == "800.00"
        assert body["splits"][0]["settled_amount"] == "800.00"
        assert body["splits"][0]["description"] == "Groceries"

        assert body["splits"][1]["id"] is not None
        assert body["splits"][1]["category_id"] == second_category["id"]
        assert body["splits"][1]["amount"] == "200.00"
        assert body["splits"][1]["settled_amount"] == "200.00"
        assert body["splits"][1]["description"] == "Household"

    async def test_create_transaction_splits_without_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """A part of the receipt may stay uncategorized — that is the honest state."""
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(None, "200.00", "Not sorted yet"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["splits"][1]["category_id"] is None
        assert body["splits"][1]["amount"] == "200.00"
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_create_transaction_splits_same_category_twice_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """Two lines of one receipt may share a category: ice cream and pasta are both food."""
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "600.00", "Ice cream"),
                split_payload(created_category["id"], "400.00", "Pasta"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert len(body["splits"]) == 2
        assert body["splits"][0]["category_id"] == created_category["id"]
        assert body["splits"][1]["category_id"] == created_category["id"]
        assert body["splits"][0]["description"] == "Ice cream"
        assert body["splits"][1]["description"] == "Pasta"

    async def test_create_transaction_splits_different_currency_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        uah_account: AccountData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """Splits state the receipt; settled amounts follow the rate of the operation."""
        payload = transaction_payload(
            amount="24.00",
            currency_code=active_currency["code"],
            settled_amount="1000.00",
            account_id=uah_account["id"],
            splits=[
                split_payload(created_category["id"], "2.00"),
                split_payload(second_category["id"], "20.00"),
                split_payload(created_category["id"], "2.00"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["amount"] == payload["amount"]
        assert body["settled_amount"] == payload["settled_amount"]
        assert body["settled_currency_code"] == uah_account["currency_code"]

        assert [split["amount"] for split in body["splits"]] == ["2.00", "20.00", "2.00"]

        assert body["splits"][0]["settled_amount"] == "83.33"
        assert body["splits"][1]["settled_amount"] == "833.33"
        assert body["splits"][2]["settled_amount"] == "83.34"

    async def test_create_transaction_splits_with_own_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(second_category["id"], "200.00"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_create_transaction_splits_sum_mismatch_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(second_category["id"], "199.99"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_create_transaction_single_split_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[split_payload(created_category["id"], "1000.00")],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_create_transaction_zero_amount_with_splits_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """A zero-amount transaction is allowed on its own, but there is nothing to split."""
        payload = transaction_payload(
            amount="0.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "0.00"),
                split_payload(second_category["id"], "0.00"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_create_transaction_splits_with_other_user_category_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        other_category = await create_category(
            client,
            category_payload(name="Other user category"),
            other_authenticated_user["headers"],
        )

        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(other_category["id"], "200.00"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_create_transaction_splits_with_archived_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        archived_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(archived_category["id"], "200.00"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transaction_splits_with_unknown_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(999, "200.00"),
            ],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_create_transaction_without_token(
        self,
        client: AsyncClient,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
        )

        response = await client.post(
            API_TRANSACTIONS,
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetTransactions:
    async def test_get_transactions_empty(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_get_transactions_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1
        assert body[0]["id"] == created_transaction["id"]
        assert body[0]["date"] == created_transaction["date"]
        assert body[0]["amount"] == created_transaction["amount"]
        assert body[0]["type"] == created_transaction["type"]
        assert body[0]["currency_code"] == created_transaction["currency_code"]
        assert body[0]["category_id"] == created_transaction["category_id"]
        assert body[0]["description"] == created_transaction["description"]
        assert body[0]["user_id"] == authenticated_user["user"]["id"]

    async def test_get_transactions_returns_only_own_transactions(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        other_account = await create_account(
            client,
            account_payload(currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        other_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="999.00",
                currency_code=active_currency["code"],
                account_id=other_account["id"],
            ),
            other_authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1

        ids = {transaction["id"] for transaction in body}

        assert created_transaction["id"] in ids
        assert other_transaction["id"] not in ids

    async def test_get_transactions_pagination_limit(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        first_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="200.00",
                currency_code=active_currency["code"],
                description="Second transaction",
                account_id=created_transaction["account_id"],
            ),
            authenticated_user["headers"],
        )

        second_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="300.00",
                currency_code=active_currency["code"],
                description="Third transaction",
                account_id=created_transaction["account_id"],
            ),
            authenticated_user["headers"],
        )

        limit = 2

        response = await client.get(
            API_TRANSACTIONS,
            params={"limit": limit},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == limit

        all_ids = {
            created_transaction["id"],
            first_transaction["id"],
            second_transaction["id"],
        }
        returned_ids = {transaction["id"] for transaction in body}

        assert len(returned_ids) == limit
        assert returned_ids.issubset(all_ids)

    async def test_get_transactions_pagination_offset(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                amount="200.00",
                currency_code=active_currency["code"],
                description="Second transaction",
                account_id=created_transaction["account_id"],
            ),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                amount="300.00",
                currency_code=active_currency["code"],
                description="Third transaction",
                account_id=created_transaction["account_id"],
            ),
            authenticated_user["headers"],
        )

        all_response = await client.get(
            API_TRANSACTIONS,
            headers=authenticated_user["headers"],
        )

        assert all_response.status_code == status.HTTP_200_OK

        all_transactions = all_response.json()

        assert len(all_transactions) == 3

        offset = 1

        offset_response = await client.get(
            API_TRANSACTIONS,
            params={"offset": offset},
            headers=authenticated_user["headers"],
        )

        assert offset_response.status_code == status.HTTP_200_OK

        offset_transactions = offset_response.json()

        assert len(offset_transactions) == len(all_transactions) - offset

        all_ids = {transaction["id"] for transaction in all_transactions}
        offset_ids = {transaction["id"] for transaction in offset_transactions}

        assert offset_ids.issubset(all_ids)

    async def test_get_transactions_transfer_sides_with_counterpart(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        uah_account: AccountData,
        created_transfer: TransferData,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 2

        sides = sides_by_account(body)

        from_side = sides[created_account["id"]]
        to_side = sides[uah_account["id"]]

        assert from_side["type"] == "EXPENSE"
        assert from_side["kind"] == "TRANSFER"
        assert from_side["amount"] == created_transfer["from_amount"]
        assert from_side["currency_code"] == created_account["currency_code"]
        assert from_side["category_id"] is None
        assert from_side["transfer_group_id"] == created_transfer["transfer_group_id"]
        assert from_side["counterpart_account_id"] == uah_account["id"]

        assert to_side["type"] == "INCOME"
        assert to_side["kind"] == "TRANSFER"
        assert to_side["amount"] == created_transfer["to_amount"]
        assert to_side["currency_code"] == uah_account["currency_code"]
        assert to_side["transfer_group_id"] == created_transfer["transfer_group_id"]
        assert to_side["counterpart_account_id"] == created_account["id"]

    async def test_get_transactions_filter_by_account_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        uah_account: AccountData,
        created_transfer: TransferData,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            params={"account_id": uah_account["id"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1
        assert body[0]["account_id"] == uah_account["id"]
        assert body[0]["type"] == "INCOME"

    async def test_get_transactions_filter_by_account_id_excludes_others(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        another_account = await create_account(
            client,
            account_payload(name="Savings", currency_code=active_currency["code"]),
            authenticated_user["headers"],
        )

        target_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        other_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="200.00",
                currency_code=active_currency["code"],
                account_id=another_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"account_id": created_account["id"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert target_transaction["id"] in ids
        assert other_transaction["id"] not in ids

    async def test_get_transactions_flags_splits_without_details(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        created_split_transaction: TransactionData,
    ):
        """The list carries the flag only: the full breakdown is one request away."""
        response = await client.get(
            API_TRANSACTIONS,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        rows = {row["id"]: row for row in response.json()}

        assert rows[created_split_transaction["id"]]["has_splits"] is True
        assert "splits" not in rows[created_split_transaction["id"]]

        assert rows[created_transaction["id"]]["has_splits"] is False
        assert "splits" not in rows[created_transaction["id"]]

    async def test_get_transactions_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.get(
            API_TRANSACTIONS,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetTransactionsFilters:
    async def test_get_transactions_filter_by_type(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        expense_transaction = await create_transaction(
            client,
            transaction_payload(
                transaction_type="EXPENSE",
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        income_transaction = await create_transaction(
            client,
            transaction_payload(
                transaction_type="INCOME",
                amount="500.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"type": "INCOME"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert income_transaction["id"] in ids
        assert expense_transaction["id"] not in ids
        assert all(transaction["type"] == "INCOME" for transaction in body)

    async def test_get_transactions_filter_by_currency_code(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        usd_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"currency_code": active_currency["code"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert usd_transaction["id"] in ids
        assert all(transaction["currency_code"] == active_currency["code"] for transaction in body)

    async def test_get_transactions_filter_currency_code_normalized(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        created_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"currency_code": active_currency["code"].lower()},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert created_transaction["id"] in ids
        assert all(transaction["currency_code"] == active_currency["code"] for transaction in body)

    async def test_get_transactions_filter_by_category_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        categorized_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="100.00",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        uncategorized_transaction = await create_transaction(
            client,
            transaction_payload(
                amount="200.00",
                currency_code=active_currency["code"],
                category_id=None,
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"category_id": created_category["id"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert categorized_transaction["id"] in ids
        assert uncategorized_transaction["id"] not in ids
        assert all(transaction["category_id"] == created_category["id"] for transaction in body)

    async def test_get_transactions_filter_by_start_date(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        old_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-01-01",
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        new_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-02-01",
                amount="200.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"start_date": "2026-02-01"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert new_transaction["id"] in ids
        assert old_transaction["id"] not in ids
        assert all(transaction["date"] >= "2026-02-01" for transaction in body)

    async def test_get_transactions_filter_by_end_date(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        old_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-01-01",
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        new_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-02-01",
                amount="200.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={"end_date": "2026-01-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert old_transaction["id"] in ids
        assert new_transaction["id"] not in ids
        assert all(transaction["date"] <= "2026-01-31" for transaction in body)

    async def test_get_transactions_filter_by_date_range(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        before_range_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-01-01",
                amount="100.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        in_range_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="200.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        after_range_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-03-10",
                amount="300.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert in_range_transaction["id"] in ids
        assert before_range_transaction["id"] not in ids
        assert after_range_transaction["id"] not in ids
        assert all("2026-02-01" <= transaction["date"] <= "2026-02-28" for transaction in body)

    async def test_get_transactions_combined_filters(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        matching_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="100.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        wrong_type_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="200.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        wrong_category_transaction = await create_transaction(
            client,
            transaction_payload(
                date="2026-02-15",
                amount="300.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTIONS,
            params={
                "type": "EXPENSE",
                "currency_code": active_currency["code"],
                "category_id": created_category["id"],
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {transaction["id"] for transaction in body}

        assert matching_transaction["id"] in ids
        assert wrong_type_transaction["id"] not in ids
        assert wrong_category_transaction["id"] not in ids

    async def test_get_transactions_invalid_date_range_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            params={
                "start_date": "2026-03-01",
                "end_date": "2026-02-01",
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "params, reason",
        [
            ({"type": "wrong"}, "invalid_type"),
            ({"currency_code": "US"}, "currency_code_too_short"),
            ({"currency_code": "USDD"}, "currency_code_too_long"),
            ({"start_date": "not-a-date"}, "invalid_start_date"),
            ({"end_date": "not-a-date"}, "invalid_end_date"),
            ({"category_id": "abc"}, "invalid_category_id"),
        ],
    )
    async def test_get_transactions_invalid_filters_fail(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        params: dict[str, object],
        reason: str,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            params=params,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()


class TestPaginationBoundaries:
    @pytest.mark.parametrize(
        "params, reason",
        [
            ({"limit": 101}, "limit_above_max"),
            ({"limit": 0}, "limit_zero"),
            ({"limit": -1}, "limit_negative"),
            ({"offset": -1}, "offset_negative"),
        ],
    )
    async def test_get_transactions_invalid_pagination_rejected(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        params: dict[str, object],
        reason: str,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            params=params,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    async def test_get_transactions_limit_at_max_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_TRANSACTIONS,
            params={"limit": 100},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK


class TestGetTransactionById:
    async def test_get_transaction_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        response = await client.get(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction["id"]
        assert body["date"] == created_transaction["date"]
        assert body["amount"] == created_transaction["amount"]
        assert body["type"] == created_transaction["type"]
        assert body["currency_code"] == created_transaction["currency_code"]
        assert body["category_id"] == created_transaction["category_id"]
        assert body["description"] == created_transaction["description"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_get_transaction_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_TRANSACTIONS}/999",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_get_transaction_regular_without_counterpart(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        """Mirror of the test above: a normal transaction must not gain transfer fields."""
        created = await create_transaction(
            client,
            transaction_payload(
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            f"{API_TRANSACTIONS}/{created['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["kind"] == "REGULAR"
        assert body["transfer_group_id"] is None
        assert body["counterpart_account_id"] is None

    async def test_get_transaction_other_user_forbidden(
        self,
        client: AsyncClient,
        other_authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        response = await client.get(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_get_transaction_invalid_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_TRANSACTIONS}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_transaction_with_splits_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_split_transaction: TransactionData,
        created_category: CategoryData,
        second_category: CategoryData,
    ):
        response = await client.get(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_split_transaction["id"]
        assert body["category_id"] is None
        assert body["has_splits"] is True

        assert len(body["splits"]) == 2

        assert body["splits"][0]["category_id"] == created_category["id"]
        assert body["splits"][0]["amount"] == "800.00"
        assert body["splits"][0]["description"] == "Groceries"

        assert body["splits"][1]["category_id"] == second_category["id"]
        assert body["splits"][1]["amount"] == "200.00"
        assert body["splits"][1]["description"] == "Household"

    async def test_get_transaction_without_splits_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        """Mirror of the test above: a plain transaction must not gain split fields."""
        response = await client.get(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["has_splits"] is False
        assert body["splits"] is None

    async def test_get_transaction_with_splits_other_user_forbidden(
        self,
        client: AsyncClient,
        other_authenticated_user: AuthenticatedUser,
        created_split_transaction: TransactionData,
    ):
        """Splits carry no owner of their own: they are reachable only through the transaction."""
        response = await client.get(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_get_transaction_without_token(
        self,
        client: AsyncClient,
        created_transaction: TransactionData,
    ):
        response = await client.get(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestUpdateTransaction:
    async def test_update_transaction_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            date="2026-05-10",
            amount="250.00",
            transaction_type="INCOME",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            description="Updated transaction",
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction["id"]
        assert body["date"] == payload["date"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["category_id"] == payload["category_id"]
        assert body["description"] == payload["description"]
        assert body["account_id"] == created_transaction["account_id"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_update_transaction_without_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            date="2026-05-10",
            amount="250.00",
            transaction_type="INCOME",
            currency_code=active_currency["code"],
            category_id=None,
            description="Updated without category",
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction["id"]
        assert body["category_id"] is None
        assert body["description"] == payload["description"]
        assert body["account_id"] == created_transaction["account_id"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_update_transaction_zero_amount_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="0.00",
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction["id"]
        assert body["amount"] == "0.00"

    async def test_update_transaction_different_currency_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        uah_account: AccountData,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="24.00",
            currency_code=active_currency["code"],
            settled_amount="1050.00",
            account_id=uah_account["id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction["id"]
        assert body["account_id"] == uah_account["id"]

        assert body["amount"] == payload["amount"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["settled_amount"] == payload["settled_amount"]
        assert body["settled_currency_code"] == uah_account["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_update_transaction_redundant_settled_amount_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="24.00",
            currency_code=active_currency["code"],
            settled_amount="1050.00",
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"], account_id=created_account["id"]
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/999",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_update_transaction_other_user_forbidden(
        self,
        client: AsyncClient,
        other_authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_update_transaction_with_other_user_category_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        other_category = await create_category(
            client,
            category_payload(
                name="Other user category for update",
            ),
            other_authenticated_user["headers"],
        )

        payload = transaction_payload(
            currency_code=active_currency["code"],
            category_id=other_category["id"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_update_transaction_with_archived_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        archived_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            category_id=archived_category["id"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_with_unknown_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            category_id=999,
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_update_transaction_with_inactive_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        inactive_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=inactive_currency["code"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_with_unknown_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        payload = transaction_payload(
            currency_code="XXX",
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_update_transaction_currency_code_normalized(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"].lower(),
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["currency_code"] == active_currency["code"]

    @pytest.mark.parametrize(
        "payload_update, reason",
        [
            ({"date": "not-a-date"}, "invalid_date_format"),
            ({"date": None}, "date_null"),
            ({"amount": "-1.00"}, "negative_amount"),
            ({"amount": None}, "amount_null"),
            ({"type": None}, "type_null"),
            ({"type": "wrong"}, "invalid_type"),
            ({"currency_code": None}, "currency_code_null"),
            ({"currency_code": "US"}, "currency_code_too_short"),
            ({"currency_code": "USDD"}, "currency_code_too_long"),
            ({"description": "x" * 1025}, "description_too_long"),
            ({"account_id": None}, "account_id_null"),
            ({"account_id": "abc"}, "account_id_not_int"),
        ],
    )
    async def test_update_transaction_validation_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
        payload_update: dict[str, object],
        reason: str,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
        )

        payload.update(payload_update)

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "missing_field",
        [
            "date",
            "amount",
            "type",
            "currency_code",
            "account_id",
        ],
    )
    async def test_update_transaction_required_fields_missing(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
        missing_field: str,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
        )

        payload.pop(missing_field)

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, missing_field
        assert "detail" in response.json()

    async def test_update_transaction_invalid_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=created_account["id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/abc",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_update_transaction_change_account_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        another_account = await create_account(
            client,
            account_payload(name="Cash", currency_code=active_currency["code"]),
            authenticated_user["headers"],
        )

        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=another_account["id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["account_id"] == another_account["id"]

    async def test_update_transaction_to_archived_account_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        archived_account: AccountData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=archived_account["id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_on_archived_account_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        archive_response = await client.delete(
            f"/api/v1/accounts/{created_transaction['account_id']}",
            headers=authenticated_user["headers"],
        )

        assert archive_response.status_code == status.HTTP_204_NO_CONTENT

        payload = transaction_payload(
            amount="777.00",
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["amount"] == "777.00"

    async def test_update_transaction_different_currency_without_settled_amount(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        second_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=second_currency["code"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_keeps_archived_category_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        created_transaction = await create_transaction(
            client,
            transaction_payload(
                category_id=created_category["id"],
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        await archive_category(
            client,
            created_category["id"],
            authenticated_user["headers"],
        )

        payload = transaction_payload(
            amount="777.00",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["amount"] == "777.00"
        assert body["category_id"] == created_category["id"]

    async def test_update_transaction_transfer_side_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_transfer: TransferData,
    ):
        """One side cannot be edited alone: the pair would go out of balance."""
        headers = authenticated_user["headers"]

        registry = await client.get(API_TRANSACTIONS, headers=headers)
        side = sides_by_account(registry.json())[created_account["id"]]

        payload = transaction_payload(
            amount="9999.00",
            currency_code=side["currency_code"],
            account_id=side["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{side['id']}",
            json=payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_replaces_splits_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_split_transaction: TransactionData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            description="ATB, corrected",
            account_id=created_split_transaction["account_id"],
            splits=[
                split_payload(created_category["id"], "700.00", "Groceries"),
                split_payload(second_category["id"], "300.00", "Household"),
            ],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_split_transaction["id"]
        assert body["description"] == payload["description"]
        assert body["has_splits"] is True

        assert len(body["splits"]) == 2
        assert body["splits"][0]["amount"] == "700.00"
        assert body["splits"][1]["amount"] == "300.00"

        get_response = await client.get(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert [split["amount"] for split in get_response.json()["splits"]] == ["700.00", "300.00"]

    async def test_update_transaction_without_splits_drops_them(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_split_transaction: TransactionData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """PUT replaces the resource: a breakdown left out of the request is gone."""
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            account_id=created_split_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["category_id"] == created_category["id"]
        assert body["has_splits"] is False
        assert body["splits"] is None

        get_response = await client.get(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert get_response.json()["has_splits"] is False
        assert get_response.json()["splits"] is None

    async def test_update_transaction_adds_splits_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
            splits=[
                split_payload(created_category["id"], "600.00"),
                split_payload(second_category["id"], "400.00"),
            ],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["category_id"] is None
        assert body["has_splits"] is True
        assert len(body["splits"]) == 2

    async def test_update_transaction_keeps_archived_split_category_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """A category archived after the fact must not make its transaction uneditable."""
        created = await create_transaction(
            client,
            transaction_payload(
                amount="1000.00",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
                splits=[
                    split_payload(created_category["id"], "800.00"),
                    split_payload(second_category["id"], "200.00"),
                ],
            ),
            authenticated_user["headers"],
        )

        await archive_category(client, second_category["id"], authenticated_user["headers"])

        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            description="Edited after archiving",
            account_id=created_account["id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(second_category["id"], "200.00"),
            ],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["description"] == payload["description"]
        assert body["splits"][1]["category_id"] == second_category["id"]

    async def test_update_transaction_new_archived_split_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
        created_category: CategoryData,
        archived_category: CategoryData,
        active_currency: CurrencyData,
    ):
        """Mirror of the test above: attaching an archived category anew is still refused."""
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(archived_category["id"], "200.00"),
            ],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transaction_splits_sum_mismatch_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_split_transaction: TransactionData,
        created_category: CategoryData,
        second_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            amount="1000.00",
            currency_code=active_currency["code"],
            account_id=created_split_transaction["account_id"],
            splits=[
                split_payload(created_category["id"], "800.00"),
                split_payload(second_category["id"], "300.00"),
            ],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_update_transaction_without_token(
        self,
        client: AsyncClient,
        created_transaction: TransactionData,
        active_currency: CurrencyData,
    ):
        payload = transaction_payload(
            currency_code=active_currency["code"],
            account_id=created_transaction["account_id"],
        )

        response = await client.put(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestDeleteTransaction:
    async def test_delete_transaction_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        response = await client.delete(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

    async def test_delete_transaction_hard_delete_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        delete_response = await client.delete(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        get_response = await client.get(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert get_response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in get_response.json()

    async def test_delete_transaction_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_TRANSACTIONS}/999",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_delete_transaction_other_user_forbidden(
        self,
        client: AsyncClient,
        other_authenticated_user: AuthenticatedUser,
        created_transaction: TransactionData,
    ):
        response = await client.delete(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_delete_transaction_invalid_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_TRANSACTIONS}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_delete_transaction_transfer_side_removes_group(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        created_transfer: TransferData,
    ):
        headers = authenticated_user["headers"]

        registry = await client.get(API_TRANSACTIONS, headers=headers)
        side = sides_by_account(registry.json())[created_account["id"]]

        response = await client.delete(
            f"{API_TRANSACTIONS}/{side['id']}",
            headers=headers,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        registry = await client.get(API_TRANSACTIONS, headers=headers)

        assert registry.json() == []

    async def test_delete_transaction_regular_removes_only_itself(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_account: AccountData,
        active_currency: CurrencyData,
        created_transfer: TransferData,
    ):
        """Mirror of the test above: the transfer branch must not fire for REGULAR."""
        headers = authenticated_user["headers"]

        regular = await create_transaction(
            client,
            transaction_payload(
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            headers,
        )

        response = await client.delete(
            f"{API_TRANSACTIONS}/{regular['id']}",
            headers=headers,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        registry = await client.get(API_TRANSACTIONS, headers=headers)

        assert len(registry.json()) == 2

    async def test_delete_transaction_with_splits_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_split_transaction: TransactionData,
    ):
        """Splits go with the transaction they explain — the database cascades them."""
        response = await client.delete(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        get_response = await client.get(
            f"{API_TRANSACTIONS}/{created_split_transaction['id']}",
            headers=authenticated_user["headers"],
        )

        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    async def test_delete_transaction_without_token(
        self,
        client: AsyncClient,
        created_transaction: TransactionData,
    ):
        response = await client.delete(
            f"{API_TRANSACTIONS}/{created_transaction['id']}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

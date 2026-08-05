import uuid

import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency

from tests.integration.endpoints.helpers import (
    transfer_payload,
    create_transfer,
    account_payload,
    create_account,
)
from tests.integration.endpoints.types import (
    AuthenticatedUser,
    AccountData,
    CurrencyData,
    TransferData,
)

API_TRANSFERS = "/api/v1/transfers"

API_TRANSACTIONS = "/api/v1/transactions"

API_ACCOUNTS = "/api/v1/accounts"


@pytest.fixture
async def same_currency_account(
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
) -> AccountData:
    """Second USD account — for same-currency transfers, where amounts must match."""
    return await create_account(
        client,
        account_payload(name="Savings", currency_code=active_currency["code"]),
        authenticated_user["headers"],
    )


async def get_balance(
        client: AsyncClient,
        account_id: int,
        headers: dict[str, str],
) -> str:
    """Read the account balance back through the API, as a serialized string."""
    response = await client.get(f"{API_ACCOUNTS}/{account_id}", headers=headers)

    assert response.status_code == status.HTTP_200_OK

    return response.json()["balance"]

class TestCreateTransfer:
    async def test_create_transfer_cross_currency_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=uah_account["id"],
            from_amount="24.00",
            to_amount="1000.00",
            description="To cash",
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["transfer_group_id"] is not None

        assert body["from_account_id"] == created_account["id"]
        assert body["from_account_name"] == created_account["name"]
        assert body["from_currency_code"] == created_account["currency_code"]
        assert body["from_amount"] == payload["from_amount"]

        assert body["to_account_id"] == uah_account["id"]
        assert body["to_account_name"] == uah_account["name"]
        assert body["to_currency_code"] == uah_account["currency_code"]
        assert body["to_amount"] == payload["to_amount"]

        assert body["exchange_rate"] == "0.0240"
        assert body["description"] == payload["description"]
        assert body["date"] == payload["date"]

    async def test_create_transfer_same_currency_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            same_currency_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["from_amount"] == body["to_amount"]

        # No conversion happened, so there is no rate to report.
        assert body["exchange_rate"] is None

    async def test_create_transfer_updates_both_balances(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
            created_transfer: TransferData,
    ):
        headers = authenticated_user["headers"]

        assert await get_balance(client, created_account["id"], headers) == "-24.00"
        assert await get_balance(client, uah_account["id"], headers) == "1000.00"

    async def test_create_transfer_excluded_from_statistics(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_transfer: TransferData,
    ):
        """Money moved between own accounts is neither income nor expense."""
        response = await client.get(
            "/api/v1/statistics/summary",
            params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        assert response.json()["currencies"] == []

    async def test_create_transfer_same_currency_different_amounts_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            same_currency_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
            from_amount="1000.00",
            to_amount="800.00",
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transfer_with_archived_account_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            archived_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=archived_account["id"],
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transfer_from_archived_account_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
            same_currency_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=archived_account["id"],
            to_account_id=same_currency_account["id"],
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transfer_with_other_user_account_forbidden(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            other_authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        other_account = await create_account(
            client,
            account_payload(currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=other_account["id"],
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_create_transfer_with_unknown_account_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=999,
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    @pytest.mark.parametrize("payload_update, reason", [
        ({"from_amount": "-1.00"}, "negative_from_amount"),
        ({"to_amount": "-1.00"}, "negative_to_amount"),
        ({"from_amount": "0.00", "to_amount": "0.00"}, "zero_amounts"),
        ({"from_amount": None}, "from_amount_null"),
        ({"to_amount": None}, "to_amount_null"),
        ({"date": "not-a-date"}, "invalid_date_format"),
        ({"date": None}, "date_null"),
        ({"description": "x" * 1025}, "description_too_long"),
        ({"from_account_id": "abc"}, "from_account_id_not_int"),
        ({"to_account_id": None}, "to_account_id_null"),
    ])
    async def test_create_transfer_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            same_currency_account: AccountData,
            payload_update: dict[str, object],
            reason: str,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
        )

        payload.update(payload_update)

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    async def test_create_transfer_to_same_account_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        """Moving money to the same account is a no-op, not a transfer."""
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=created_account["id"],
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    @pytest.mark.parametrize("missing_field", [
        "from_account_id",
        "to_account_id",
        "from_amount",
        "to_amount",
        "date",
    ])
    async def test_create_transfer_required_fields_missing(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            same_currency_account: AccountData,
            missing_field: str,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
        )

        payload.pop(missing_field)

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, missing_field
        assert "detail" in response.json()

    async def test_create_transfer_with_deactivated_currency_fails(
            self,
            client: AsyncClient,
            test_session: AsyncSession,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
            second_currency: CurrencyData,
    ):
        """A currency switched off by an admin blocks new records, transfers included."""
        currency = await test_session.get(Currency, second_currency["code"])
        currency.is_active = False
        await test_session.commit()

        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=uah_account["id"],
            from_amount="24.00",
            to_amount="1000.00",
        )

        response = await client.post(
            API_TRANSFERS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_transfer_without_token(
            self,
            client: AsyncClient,
            created_account: AccountData,
            same_currency_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
        )

        response = await client.post(API_TRANSFERS, json=payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetTransfer:
    async def test_get_transfer_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_transfer: TransferData,
    ):
        response = await client.get(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        assert response.json() == created_transfer

    async def test_get_transfer_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_TRANSFERS}/{uuid.uuid4()}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_get_transfer_other_user_not_found(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_transfer: TransferData,
    ):
        """A group id is not a resource id: someone else's group simply does not exist."""
        response = await client.get(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_get_transfer_invalid_id(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_TRANSFERS}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_transfer_without_token(
            self,
            client: AsyncClient,
            created_transfer: TransferData,
    ):
        response = await client.get(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestUpdateTransfer:
    async def test_update_transfer_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
            created_transfer: TransferData,
    ):
        headers = authenticated_user["headers"]

        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=uah_account["id"],
            from_amount="48.00",
            to_amount="2000.00",
            date="2026-02-01",
            description="Doubled",
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            json=payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["transfer_group_id"] == created_transfer["transfer_group_id"]
        assert body["from_amount"] == payload["from_amount"]
        assert body["to_amount"] == payload["to_amount"]
        assert body["description"] == payload["description"]
        assert body["date"] == payload["date"]

        assert await get_balance(client, created_account["id"], headers) == "-48.00"
        assert await get_balance(client, uah_account["id"], headers) == "2000.00"

    async def test_update_transfer_swap_accounts_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
            created_transfer: TransferData,
    ):
        """Swapping from/to must flip both sides, not leave two rows in one direction."""
        headers = authenticated_user["headers"]

        payload = transfer_payload(
            from_account_id=uah_account["id"],
            to_account_id=created_account["id"],
            from_amount="1000.00",
            to_amount="24.00",
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            json=payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK

        assert await get_balance(client, created_account["id"], headers) == "24.00"
        assert await get_balance(client, uah_account["id"], headers) == "-1000.00"

    async def test_update_transfer_on_archived_account_allowed(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
            created_transfer: TransferData,
    ):
        """Archiving forbids new usage, not fixing a typo in what already exists."""
        headers = authenticated_user["headers"]

        archive_response = await client.delete(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=headers,
        )

        assert archive_response.status_code == status.HTTP_204_NO_CONTENT

        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=uah_account["id"],
            from_amount="30.00",
            to_amount="1200.00",
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            json=payload,
            headers=headers,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["from_amount"] == "30.00"

    async def test_update_transfer_to_archived_account_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            archived_account: AccountData,
            created_transfer: TransferData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=archived_account["id"],
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transfer_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            same_currency_account: AccountData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
        )

        response = await client.put(
            f"{API_TRANSFERS}/{uuid.uuid4()}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_update_transfer_other_user_not_found(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_transfer: TransferData,
            active_currency: CurrencyData,
    ):
        other_account = await create_account(
            client,
            account_payload(currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        another_other_account = await create_account(
            client,
            account_payload(name="Other cash", currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        payload = transfer_payload(
            from_account_id=other_account["id"],
            to_account_id=another_other_account["id"],
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_update_transfer_same_currency_different_amounts_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            same_currency_account: AccountData,
    ):
        created = await create_transfer(
            client,
            transfer_payload(
                from_account_id=created_account["id"],
                to_account_id=same_currency_account["id"],
            ),
            authenticated_user["headers"],
        )

        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
            from_amount="1000.00",
            to_amount="800.00",
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created['transfer_group_id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_transfer_without_token(
            self,
            client: AsyncClient,
            created_account: AccountData,
            same_currency_account: AccountData,
            created_transfer: TransferData,
    ):
        payload = transfer_payload(
            from_account_id=created_account["id"],
            to_account_id=same_currency_account["id"],
        )

        response = await client.put(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestDeleteTransfer:
    async def test_delete_transfer_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            uah_account: AccountData,
            created_transfer: TransferData,
    ):
        headers = authenticated_user["headers"]

        response = await client.delete(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=headers,
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

        assert await get_balance(client, created_account["id"], headers) == "0.00"
        assert await get_balance(client, uah_account["id"], headers) == "0.00"

        registry = await client.get(API_TRANSACTIONS, headers=headers)

        assert registry.json() == []

    async def test_delete_transfer_hard_delete_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_transfer: TransferData,
    ):
        delete_response = await client.delete(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=authenticated_user["headers"],
        )

        assert delete_response.status_code == status.HTTP_204_NO_CONTENT

        get_response = await client.get(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=authenticated_user["headers"],
        )

        assert get_response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in get_response.json()

    async def test_delete_transfer_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_TRANSFERS}/{uuid.uuid4()}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_delete_transfer_other_user_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            other_authenticated_user: AuthenticatedUser,
            created_transfer: TransferData,
    ):
        response = await client.delete(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

        # The owner still sees it.
        get_response = await client.get(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
            headers=authenticated_user["headers"],
        )

        assert get_response.status_code == status.HTTP_200_OK

    async def test_delete_transfer_without_token(
            self,
            client: AsyncClient,
            created_transfer: TransferData,
    ):
        response = await client.delete(
            f"{API_TRANSFERS}/{created_transfer['transfer_group_id']}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

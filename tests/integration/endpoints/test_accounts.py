import pytest
from fastapi import status
from httpx import AsyncClient

from tests.integration.endpoints.helpers import account_payload, create_account, create_transaction, transaction_payload
from tests.integration.endpoints.types import AuthenticatedUser, CurrencyData, AccountData

API_ACCOUNTS = "/api/v1/accounts"


class TestCreateAccount:
    async def test_create_account_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])

        response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None
        assert body["name"] == payload["name"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert body["created_at"] is not None
        assert body["archived_at"] is None
        assert body["balance"] == "0.00"

    @pytest.mark.parametrize("name, reason", [
        ("a", "min_length_allowed"),
        ("a" * 100, "max_length_allowed"),
        ("Card *4242", "special_chars_allowed"),
        ("Cash (home)", "brackets_allowed"),
    ])
    async def test_create_account_valid_names(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            name: str,
            reason: str,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(name=name, currency_code=active_currency["code"]),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED, reason
        assert response.json()["name"] == name

    async def test_create_account_name_is_stripped(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(name="  Monobank  ", currency_code=active_currency["code"]),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["name"] == "Monobank"

    async def test_create_account_name_at_max_length_after_strip(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        name = "Monobank" + " " * 95

        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(name=name, currency_code=active_currency["code"]),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["name"] == "Monobank"

    async def test_create_account_duplicate_name(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(
                name=created_account["name"],
                currency_code=active_currency["code"],
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_account_with_archived_name_conflicts(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
            active_currency: CurrencyData,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(
                name=archived_account["name"],
                currency_code=active_currency["code"],
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_account_same_name_allowed_for_other_user(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            other_authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])

        first_response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert first_response.status_code == status.HTTP_201_CREATED
        assert first_response.json()["user_id"] == authenticated_user["user"]["id"]

        second_response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert second_response.status_code == status.HTTP_201_CREATED
        assert second_response.json()["user_id"] == other_authenticated_user["user"]["id"]

    async def test_create_account_with_inactive_currency_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            inactive_currency: CurrencyData,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(currency_code=inactive_currency["code"]),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_account_with_unknown_currency_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(currency_code="XXX"),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_create_account_currency_code_normalized(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(currency_code=active_currency["code"].lower()),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["currency_code"] == active_currency["code"]

    @pytest.mark.parametrize("payload_update, reason", [
        ({"name": ""}, "empty_name"),
        ({"name": "   "}, "blank_name"),
        ({"name": "a" * 101}, "name_too_long"),
        ({"name": None}, "name_null"),
        ({"currency_code": None}, "currency_code_null"),
        ({"currency_code": "US"}, "currency_code_too_short"),
        ({"currency_code": "USDD"}, "currency_code_too_long"),
        ({"initial_balance": "abc"}, "initial_balance_not_decimal"),
        ({"initial_balance_kind": "WRONG"}, "initial_balance_kind_invalid"),
    ])
    async def test_create_account_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            payload_update: dict[str, object],
            reason: str,
    ):
        payload = account_payload(currency_code=active_currency["code"])

        payload.update(payload_update)

        response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    @pytest.mark.parametrize("missing_field", [
        "name",
        "currency_code",
    ])
    async def test_create_account_required_fields_missing(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
            missing_field: str,
    ):
        payload = account_payload(currency_code=active_currency["code"])

        payload.pop(missing_field)

        response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, missing_field
        assert "detail" in response.json()

    async def test_create_account_with_existing_initial_balance(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])
        payload["initial_balance"] = "5000.00"
        payload["initial_balance_kind"] = "EXISTING"

        response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["balance"] == "5000.00"

        account_id = response.json()["id"]

        get_response = await client.get(
            f"{API_ACCOUNTS}/{account_id}",
            headers=authenticated_user["headers"],
        )

        assert get_response.json()["balance"] == "5000.00"

    async def test_create_account_with_negative_initial_balance(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])
        payload["initial_balance"] = "-2000.00"

        response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["balance"] == "-2000.00"

    async def test_create_account_existing_balance_excluded_from_statistics(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])
        payload["initial_balance"] = "5000.00"
        payload["initial_balance_kind"] = "EXISTING"

        await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        response = await client.get(
            "/api/v1/statistics/summary",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["currencies"] == []

    async def test_create_account_received_balance_counted_in_statistics(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])
        payload["initial_balance"] = "5000.00"
        payload["initial_balance_kind"] = "RECEIVED"

        await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        response = await client.get(
            "/api/v1/statistics/summary",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        currencies = response.json()["currencies"]

        assert len(currencies) == 1
        assert currencies[0]["income"] == "5000.00"

    async def test_create_account_initial_balance_appears_in_transactions(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            active_currency: CurrencyData,
    ):
        payload = account_payload(currency_code=active_currency["code"])
        payload["initial_balance"] = "5000.00"

        create_response = await client.post(
            API_ACCOUNTS,
            json=payload,
            headers=authenticated_user["headers"],
        )

        account_id = create_response.json()["id"]

        response = await client.get(
            "/api/v1/transactions",
            headers=authenticated_user["headers"],
        )

        body = response.json()

        assert len(body) == 1
        assert body[0]["kind"] == "ADJUSTMENT"
        assert body[0]["type"] == "INCOME"
        assert body[0]["amount"] == "5000.00"
        assert body[0]["account_id"] == account_id

    async def test_create_account_without_token(
            self,
            client: AsyncClient,
            active_currency: CurrencyData,
    ):
        response = await client.post(
            API_ACCOUNTS,
            json=account_payload(currency_code=active_currency["code"]),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetAccounts:
    async def test_get_accounts_empty(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(API_ACCOUNTS, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    async def test_get_accounts_default_returns_active(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            archived_account: AccountData,
    ):
        response = await client.get(API_ACCOUNTS, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1
        assert body[0]["id"] == created_account["id"]
        assert body[0]["archived_at"] is None

    async def test_get_accounts_status_archived(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            archived_account: AccountData,
    ):
        response = await client.get(
            API_ACCOUNTS,
            headers=authenticated_user["headers"],
            params={"account_status": "archived"},
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1
        assert body[0]["id"] == archived_account["id"]
        assert body[0]["archived_at"] is not None

    async def test_get_accounts_status_all(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            archived_account: AccountData,
    ):
        response = await client.get(
            API_ACCOUNTS,
            headers=authenticated_user["headers"],
            params={"account_status": "all"},
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {account["id"] for account in body}

        assert len(body) == 2
        assert created_account["id"] in ids
        assert archived_account["id"] in ids

    async def test_get_accounts_returns_only_own(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            other_authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        other_account = await create_account(
            client,
            account_payload(name="Other Account", currency_code=active_currency["code"]),
            other_authenticated_user["headers"],
        )

        response = await client.get(API_ACCOUNTS, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        ids = {account["id"] for account in body}

        assert len(body) == 1
        assert created_account["id"] in ids
        assert other_account["id"] not in ids

    async def test_get_accounts_invalid_status(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_ACCOUNTS,
            headers=authenticated_user["headers"],
            params={"account_status": "wrong_status"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_accounts_returns_balances(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        empty_account = await create_account(
            client,
            account_payload(name="Empty", currency_code=active_currency["code"]),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                amount="500.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(API_ACCOUNTS, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK

        by_id = {account["id"]: account for account in response.json()}

        assert by_id[created_account["id"]]["balance"] == "500.00"
        assert by_id[empty_account["id"]]["balance"] == "0.00"

    async def test_get_accounts_without_token(
            self,
            client: AsyncClient,
    ):
        response = await client.get(API_ACCOUNTS)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetAccountById:
    async def test_get_account_by_id_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.get(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_account["id"]
        assert body["name"] == created_account["name"]
        assert body["currency_code"] == created_account["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_get_account_by_id_archived_allowed(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
    ):
        response = await client.get(
            f"{API_ACCOUNTS}/{archived_account['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["archived_at"] is not None

    async def test_get_account_by_id_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_ACCOUNTS}/999",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_get_account_by_id_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.get(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_get_account_by_id_invalid_id(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_ACCOUNTS}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_get_account_by_id_returns_balance(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                amount="1000.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        await create_transaction(
            client,
            transaction_payload(
                amount="300.00",
                transaction_type="EXPENSE",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.get(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["balance"] == "700.00"

    async def test_get_account_by_id_without_token(
            self,
            client: AsyncClient,
            created_account: AccountData,
    ):
        response = await client.get(f"{API_ACCOUNTS}/{created_account['id']}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestUpdateAccount:
    async def test_update_account_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{created_account['id']}",
            json={"name": "Renamed Account"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_account["id"]
        assert body["name"] == "Renamed Account"
        assert body["currency_code"] == created_account["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_update_account_ignores_currency_code(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            inactive_currency: CurrencyData,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{created_account['id']}",
            json={"name": "Renamed Account", "currency_code": inactive_currency["code"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["currency_code"] == created_account["currency_code"]

    async def test_update_account_archived_allowed(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{archived_account['id']}",
            json={"name": "Renamed Closed Card"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["name"] == "Renamed Closed Card"
        assert body["archived_at"] is not None

    async def test_update_account_same_name_allowed(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{created_account['id']}",
            json={"name": created_account["name"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == created_account["name"]

    async def test_update_account_duplicate_name(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        other_account = await create_account(
            client,
            account_payload(name="Cash", currency_code=active_currency["code"]),
            authenticated_user["headers"],
        )

        response = await client.put(
            f"{API_ACCOUNTS}/{other_account['id']}",
            json={"name": created_account["name"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_update_account_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/999",
            json={"name": "Renamed Account"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_update_account_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{created_account['id']}",
            json={"name": "Renamed Account"},
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    @pytest.mark.parametrize("payload, reason", [
        ({"name": ""}, "empty_name"),
        ({"name": "   "}, "blank_name"),
        ({"name": "a" * 101}, "name_too_long"),
        ({"name": None}, "name_null"),
        ({}, "missing_name"),
    ])
    async def test_update_account_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            payload: dict[str, object],
            reason: str,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{created_account['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    async def test_update_account_invalid_id(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/abc",
            json={"name": "Renamed Account"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_update_account_without_token(
            self,
            client: AsyncClient,
            created_account: AccountData,
    ):
        response = await client.put(
            f"{API_ACCOUNTS}/{created_account['id']}",
            json={"name": "Renamed Account"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestArchiveAccount:
    async def test_archive_account_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.delete(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

        active_response = await client.get(
            API_ACCOUNTS,
            headers=authenticated_user["headers"],
        )

        assert active_response.json() == []

        archived_response = await client.get(
            API_ACCOUNTS,
            headers=authenticated_user["headers"],
            params={"account_status": "archived"},
        )

        archived_accounts = archived_response.json()

        assert len(archived_accounts) == 1
        assert archived_accounts[0]["id"] == created_account["id"]
        assert archived_accounts[0]["archived_at"] is not None

    async def test_archive_account_already_archived(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
    ):
        response = await client.delete(
            f"{API_ACCOUNTS}/{archived_account['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_archive_account_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_ACCOUNTS}/999",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_archive_account_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.delete(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_archive_account_invalid_id(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_ACCOUNTS}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_archive_account_without_token(
            self,
            client: AsyncClient,
            created_account: AccountData,
    ):
        response = await client.delete(f"{API_ACCOUNTS}/{created_account['id']}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestRestoreAccount:
    async def test_restore_account_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{archived_account['id']}/restore",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == archived_account["id"]
        assert body["name"] == archived_account["name"]
        assert body["archived_at"] is None

        active_response = await client.get(
            API_ACCOUNTS,
            headers=authenticated_user["headers"],
        )

        active_accounts = active_response.json()

        assert len(active_accounts) == 1
        assert active_accounts[0]["id"] == archived_account["id"]

    async def test_restore_account_not_archived(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/restore",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_restore_account_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/999/restore",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    async def test_restore_account_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{archived_account['id']}/restore",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_restore_account_without_token(
            self,
            client: AsyncClient,
            archived_account: AccountData,
    ):
        response = await client.post(f"{API_ACCOUNTS}/{archived_account['id']}/restore")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestReconcileAccount:
    async def test_reconcile_account_positive_difference(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                amount="1000.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "1300.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["adjusted"] is True
        assert body["difference"] == "300.00"
        assert body["account"]["balance"] == "1300.00"

        get_response = await client.get(
            f"{API_ACCOUNTS}/{created_account['id']}",
            headers=authenticated_user["headers"],
        )

        assert get_response.json()["balance"] == "1300.00"

    async def test_reconcile_account_negative_difference(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                amount="1000.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "700.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["adjusted"] is True
        assert body["difference"] == "-300.00"
        assert body["account"]["balance"] == "700.00"

    async def test_reconcile_account_creates_adjustment_transaction(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "500.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        transactions_response = await client.get(
            "/api/v1/transactions",
            headers=authenticated_user["headers"],
        )

        body = transactions_response.json()

        assert len(body) == 1
        assert body[0]["kind"] == "ADJUSTMENT"
        assert body[0]["type"] == "INCOME"
        assert body[0]["amount"] == "500.00"
        assert body[0]["account_id"] == created_account["id"]
        assert body[0]["currency_code"] == created_account["currency_code"]

    async def test_reconcile_account_excluded_from_statistics(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "5000.00"},
            headers=authenticated_user["headers"],
        )

        response = await client.get(
            "/api/v1/statistics/summary",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["currencies"] == []

    async def test_reconcile_account_no_difference(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                amount="1000.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "1000.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["adjusted"] is False
        assert body["difference"] == "0.00"
        assert body["account"]["balance"] == "1000.00"

        transactions_response = await client.get(
            "/api/v1/transactions",
            headers=authenticated_user["headers"],
        )

        assert len(transactions_response.json()) == 1

    async def test_reconcile_account_to_zero(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            active_currency: CurrencyData,
    ):
        await create_transaction(
            client,
            transaction_payload(
                amount="500.00",
                transaction_type="INCOME",
                currency_code=active_currency["code"],
                account_id=created_account["id"],
            ),
            authenticated_user["headers"],
        )

        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "0"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["adjusted"] is True
        assert body["difference"] == "-500.00"
        assert body["account"]["balance"] == "0.00"

    async def test_reconcile_account_archived_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            archived_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{archived_account['id']}/reconcile",
            json={"actual_balance": "500.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_reconcile_account_other_user_forbidden(
            self,
            client: AsyncClient,
            other_authenticated_user: AuthenticatedUser,
            created_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "500.00"},
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    async def test_reconcile_account_not_found(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/999/reconcile",
            json={"actual_balance": "500.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "detail" in response.json()

    @pytest.mark.parametrize("payload, reason", [
        ({}, "missing_actual_balance"),
        ({"actual_balance": None}, "actual_balance_null"),
        ({"actual_balance": "abc"}, "actual_balance_not_decimal"),
    ])
    async def test_reconcile_account_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            created_account: AccountData,
            payload: dict[str, object],
            reason: str,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    async def test_reconcile_account_invalid_id(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/abc/reconcile",
            json={"actual_balance": "500.00"},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_reconcile_account_without_token(
            self,
            client: AsyncClient,
            created_account: AccountData,
    ):
        response = await client.post(
            f"{API_ACCOUNTS}/{created_account['id']}/reconcile",
            json={"actual_balance": "500.00"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

import pytest
from fastapi import status

from httpx import AsyncClient

from tests.integration.endpoints.types import (
    CategoryData,
    CurrencyData,
    AuthenticatedUser,
    TransactionTemplateData,
    AccountData,
)
from tests.integration.endpoints.helpers import (
    transaction_template_payload,
    create_transaction_template,
    archive_category,
)

API_TRANSACTION_TEMPLATES = "/api/v1/transactions/templates"


@pytest.fixture
async def created_transaction_template(
    client: AsyncClient,
    authenticated_user: AuthenticatedUser,
    active_currency: CurrencyData,
):
    payload = transaction_template_payload(
        currency_code=active_currency["code"],
    )

    return await create_transaction_template(client, payload, authenticated_user["headers"])


class TestCreateTransactionTemplate:
    async def test_create_template_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            description="Daily lunch",
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None

        assert body["name"] == payload["name"]

        assert body["amount"] == payload["amount"]

        assert body["type"] == payload["type"]

        assert body["currency_code"] == payload["currency_code"]

        assert body["category_id"] == payload["category_id"]

        assert body["description"] == payload["description"]

        assert body["user_id"] == authenticated_user["user"]["id"]

        assert body["created_at"] is not None

    async def test_create_template_without_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None

        assert body["name"] == payload["name"]

        assert body["amount"] == payload["amount"]

        assert body["type"] == payload["type"]

        assert body["currency_code"] == payload["currency_code"]

        assert body["category_id"] is None

        assert body["description"] == payload["description"]

        assert body["user_id"] == authenticated_user["user"]["id"]

        assert body["created_at"] is not None

    async def test_create_template_zero_amount_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            amount="0.00",
            currency_code=active_currency["code"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None

        assert body["amount"] == payload["amount"]

        assert body["user_id"] == authenticated_user["user"]["id"]

        assert body["created_at"] is not None

    async def test_create_template_duplicate_name(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["id"] is not None

        assert body["user_id"] == authenticated_user["user"]["id"]

        assert body["created_at"] is not None

        duplicate_response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert duplicate_response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in duplicate_response.json()

    async def test_create_template_same_name_for_different_users_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        assert response.json()["user_id"] == authenticated_user["user"]["id"]

        other_user_response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert other_user_response.status_code == status.HTTP_201_CREATED

        assert other_user_response.json()["user_id"] == other_authenticated_user["user"]["id"]

    async def test_create_template_with_other_user_category_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_create_template_with_archived_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        archived_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
            category_id=archived_category["id"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_create_template_with_unknown_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
            category_id=999,
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_create_template_with_inactive_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        inactive_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=inactive_currency["code"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_create_template_with_unknown_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        payload = transaction_template_payload(
            currency_code="XXX",
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_create_template_currency_code_normalized(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"].lower(),
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        assert response.json()["currency_code"] == active_currency["code"]

    @pytest.mark.parametrize(
        "payload_update, reason",
        [
            ({"name": ""}, "empty_name"),
            ({"name": "   "}, "blank_name"),
            ({"name": "a" * 101}, "name_too_long"),
            ({"name": None}, "name_null"),
            ({"amount": "-1.00"}, "negative_amount"),
            ({"amount": None}, "amount_null"),
            ({"type": None}, "type_null"),
            ({"type": "wrong"}, "invalid_type"),
            ({"currency_code": None}, "currency_code_null"),
            ({"currency_code": "US"}, "currency_code_too_short"),
            ({"currency_code": "USDD"}, "currency_code_too_long"),
            ({"description": "x" * 1025}, "description_too_long"),
        ],
    )
    async def test_create_template_validation_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
        payload_update: dict[str, object],
        reason: str,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        payload.update(payload_update)

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "missing_field",
        [
            "name",
            "amount",
            "type",
            "currency_code",
        ],
    )
    async def test_create_template_required_fields_missing(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
        missing_field: str,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        payload.pop(missing_field)

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, missing_field
        assert "detail" in response.json()

    async def test_create_template_without_token(
        self,
        client: AsyncClient,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        response = await client.post(
            API_TRANSACTION_TEMPLATES,
            json=payload,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestGetTransactionTemplates:
    async def test_get_templates_empty(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_TRANSACTION_TEMPLATES,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        assert response.json() == []

    async def test_get_templates_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.get(
            API_TRANSACTION_TEMPLATES,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1

        assert body[0]["id"] == created_transaction_template["id"]

        assert body[0]["name"] == created_transaction_template["name"]

        assert body[0]["user_id"] == authenticated_user["user"]["id"]

    async def test_get_templates_returns_only_own_templates(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        other_user_transaction_template = await create_transaction_template(
            client,
            transaction_template_payload(
                name=created_transaction_template["name"],
                currency_code=created_transaction_template["currency_code"],
            ),
            other_authenticated_user["headers"],
        )

        response = await client.get(
            API_TRANSACTION_TEMPLATES,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert len(body) == 1

        assert body[0]["id"] == created_transaction_template["id"]
        assert body[0]["name"] == created_transaction_template["name"]
        assert body[0]["user_id"] == authenticated_user["user"]["id"]

        ids = {template["id"] for template in body}

        assert other_user_transaction_template["id"] not in ids

    async def test_get_templates_pagination_limit(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        first_template = await create_transaction_template(
            client,
            transaction_template_payload(
                name="Salary",
                amount="800.00",
                currency_code=created_transaction_template["currency_code"],
            ),
            authenticated_user["headers"],
        )

        second_template = await create_transaction_template(
            client,
            transaction_template_payload(
                name="Travel",
                amount="255.00",
                currency_code=created_transaction_template["currency_code"],
            ),
            authenticated_user["headers"],
        )

        limit = 2

        limited_response = await client.get(
            API_TRANSACTION_TEMPLATES,
            headers=authenticated_user["headers"],
            params={"limit": limit},
        )

        assert limited_response.status_code == status.HTTP_200_OK

        limited_templates = limited_response.json()

        assert len(limited_templates) == limit

        all_ids = {
            item["id"]
            for item in [
                created_transaction_template,
                first_template,
                second_template,
            ]
        }

        limited_ids = {item["id"] for item in limited_templates}

        assert len(limited_ids) == limit
        assert limited_ids.issubset(all_ids)

    async def test_get_templates_pagination_offset(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        await create_transaction_template(
            client,
            transaction_template_payload(
                name="Salary",
                amount="800.00",
                currency_code=created_transaction_template["currency_code"],
            ),
            authenticated_user["headers"],
        )

        await create_transaction_template(
            client,
            transaction_template_payload(
                name="Travel",
                amount="255.00",
                currency_code=created_transaction_template["currency_code"],
            ),
            authenticated_user["headers"],
        )

        all_response = await client.get(
            API_TRANSACTION_TEMPLATES,
            headers=authenticated_user["headers"],
        )

        assert all_response.status_code == status.HTTP_200_OK

        all_templates = all_response.json()

        assert len(all_templates) == 3

        offset = 1

        offset_response = await client.get(
            API_TRANSACTION_TEMPLATES,
            headers=authenticated_user["headers"],
            params={"offset": offset},
        )

        assert offset_response.status_code == status.HTTP_200_OK

        offset_templates = offset_response.json()

        assert len(offset_templates) == len(all_templates) - offset

        all_ids = {item["id"] for item in all_templates}
        offset_ids = {item["id"] for item in offset_templates}

        assert len(offset_ids) == 2

        assert offset_ids.issubset(all_ids)

    async def test_get_templates_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.get(
            API_TRANSACTION_TEMPLATES,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestTemplatePaginationBoundaries:
    async def test_get_templates_limit_above_max_rejected(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_TRANSACTION_TEMPLATES,
            params={"limit": 101},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()


class TestGetTransactionTemplateById:
    async def test_get_template_by_id_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.get(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction_template["id"]
        assert body["name"] == created_transaction_template["name"]
        assert body["amount"] == created_transaction_template["amount"]
        assert body["currency_code"] == created_transaction_template["currency_code"]
        assert body["category_id"] == created_transaction_template["category_id"]
        assert body["description"] == created_transaction_template["description"]
        assert body["type"] == created_transaction_template["type"]
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert body["created_at"] is not None

    async def test_get_template_by_id_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_TRANSACTION_TEMPLATES}/999",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_get_template_by_id_other_user_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.get(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_get_template_by_id_without_token(
        self,
        client: AsyncClient,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.get(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}"
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

    async def test_get_template_by_id_invalid_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            f"{API_TRANSACTION_TEMPLATES}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        assert "detail" in response.json()


class TestUpdateTransactionTemplate:
    async def test_update_template_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Updated template",
            amount="250.00",
            template_type="EXPENSE",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
            description="Updated description",
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction_template["id"]
        assert body["name"] == payload["name"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert body["category_id"] == payload["category_id"]
        assert body["description"] == payload["description"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert body["created_at"] is not None

    async def test_update_template_without_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Updated template",
            amount="250.00",
            template_type="EXPENSE",
            currency_code=active_currency["code"],
            description="Updated description",
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["id"] == created_transaction_template["id"]
        assert body["name"] == payload["name"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert body["category_id"] is None
        assert body["description"] == payload["description"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert body["created_at"] is not None

    async def test_update_template_zero_amount_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Updated template",
            amount="0.00",
            currency_code=active_currency["code"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["id"] == created_transaction_template["id"]
        assert body["amount"] == payload["amount"]
        assert body["type"] == payload["type"]
        assert body["category_id"] is None
        assert body["description"] == payload["description"]
        assert body["currency_code"] == payload["currency_code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    async def test_update_template_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Updated template",
            amount="250.00",
            currency_code=active_currency["code"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/999",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_update_template_other_user_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Updated template",
            amount="250.00",
            currency_code=active_currency["code"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_update_template_duplicate_name_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Salary",
            currency_code=active_currency["code"],
        )

        other_template = await create_transaction_template(
            client,
            payload,
            authenticated_user["headers"],
        )

        payload = transaction_template_payload(
            name=created_transaction_template["name"],
            currency_code=active_currency["code"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{other_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_update_template_same_name_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name=created_transaction_template["name"],
            currency_code=active_currency["code"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["id"] == created_transaction_template["id"]
        assert body["name"] == payload["name"]
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert body["created_at"] is not None

    async def test_update_template_with_other_user_category_forbidden(
        self,
        client: AsyncClient,
        other_authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        other_template = await create_transaction_template(
            client,
            transaction_template_payload(
                name="Updated template",
                amount="250.00",
                currency_code=active_currency["code"],
            ),
            other_authenticated_user["headers"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{other_template['id']}",
            json=transaction_template_payload(
                name="Updated template",
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_update_template_with_archived_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        archived_category: CategoryData,
        active_currency: CurrencyData,
    ):
        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=transaction_template_payload(
                name="Updated template",
                currency_code=active_currency["code"],
                category_id=archived_category["id"],
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_update_template_with_unknown_category_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=transaction_template_payload(
                name="Updated template",
                currency_code=active_currency["code"],
                category_id=999,
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_update_template_with_inactive_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        inactive_currency: CurrencyData,
    ):
        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=transaction_template_payload(
                name="Updated template", currency_code=inactive_currency["code"]
            ),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_update_template_with_unknown_currency_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=transaction_template_payload(name="Updated template", currency_code="XXX"),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_update_template_currency_code_normalized(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        payload = transaction_template_payload(
            name="Updated template",
            currency_code=active_currency["code"].lower(),
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == created_transaction_template["id"]
        assert body["currency_code"] == active_currency["code"]
        assert body["user_id"] == authenticated_user["user"]["id"]

    @pytest.mark.parametrize(
        "payload_update, reason",
        [
            ({"name": ""}, "empty_name"),
            ({"name": "   "}, "blank_name"),
            ({"name": "a" * 101}, "name_too_long"),
            ({"name": None}, "name_null"),
            ({"amount": "-1.00"}, "negative_amount"),
            ({"amount": None}, "amount_null"),
            ({"type": None}, "type_null"),
            ({"type": "wrong"}, "invalid_type"),
            ({"currency_code": None}, "currency_code_null"),
            ({"currency_code": "US"}, "currency_code_too_short"),
            ({"currency_code": "USDD"}, "currency_code_too_long"),
            ({"description": "x" * 1025}, "description_too_long"),
        ],
    )
    async def test_update_template_validation_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
        payload_update: dict[str, object],
        reason: str,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        payload.update(payload_update)

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    @pytest.mark.parametrize(
        "missing_field",
        [
            "name",
            "amount",
            "type",
            "currency_code",
        ],
    )
    async def test_update_template_required_fields_missing(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
        missing_field: str,
    ):
        payload = transaction_template_payload(
            currency_code=active_currency["code"],
        )

        payload.pop(missing_field)

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

    async def test_update_template_keeps_archived_category_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        active_currency: CurrencyData,
    ):
        created_transaction_template = await create_transaction_template(
            client,
            transaction_template_payload(
                currency_code=active_currency["code"],
                category_id=created_category["id"],
            ),
            authenticated_user["headers"],
        )
        await archive_category(
            client,
            created_category["id"],
            authenticated_user["headers"],
        )

        payload = transaction_template_payload(
            name="Renamed template",
            currency_code=active_currency["code"],
            category_id=created_category["id"],
        )

        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["name"] == "Renamed template"
        assert body["category_id"] == created_category["id"]

    async def test_update_template_without_token(
        self,
        client: AsyncClient,
        created_transaction_template: TransactionTemplateData,
        active_currency: CurrencyData,
    ):
        response = await client.put(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            json=transaction_template_payload(
                currency_code=active_currency["code"],
            ),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestDeleteTransactionTemplate:
    async def test_delete_template_hard_delete_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.delete(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        assert response.content == b""

        not_found_response = await client.delete(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            headers=authenticated_user["headers"],
        )

        assert not_found_response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in not_found_response.json()

    async def test_delete_template_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_TRANSACTION_TEMPLATES}/999",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_delete_template_other_user_forbidden(
        self,
        client: AsyncClient,
        other_authenticated_user: AuthenticatedUser,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.delete(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_delete_template_without_token(
        self,
        client: AsyncClient,
        created_transaction_template: TransactionTemplateData,
    ):
        response = await client.delete(
            f"{API_TRANSACTION_TEMPLATES}/{created_transaction_template['id']}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

    async def test_delete_template_invalid_id(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_TRANSACTION_TEMPLATES}/abc",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert "detail" in response.json()

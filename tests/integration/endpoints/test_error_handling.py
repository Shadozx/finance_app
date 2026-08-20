from pytest_mock import MockerFixture
from fastapi import status
from httpx import AsyncClient

from app.repositories import CategoryRepository

from tests.integration.endpoints.helpers import category_payload, create_category
from tests.integration.endpoints.types import AuthenticatedUser

API_CATEGORIES = "/api/v1/categories"


class TestIntegrityErrorHandler:
    async def test_integrity_unique_violation_conflict(
        self,
        mocker: MockerFixture,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        """The unique constraint is the last line of defence: if the service check
        is bypassed (as under a race), the DB error must surface as 409, not 500."""
        payload = category_payload(name="same name")

        await create_category(client, payload, authenticated_user["headers"])

        mocker.patch.object(
            CategoryRepository,
            "get_by_user_and_name",
            return_value=None,
        )

        response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

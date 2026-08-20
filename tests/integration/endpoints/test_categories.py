import pytest
from fastapi import status
from httpx import AsyncClient

from tests.integration.endpoints.helpers import category_payload, create_category, archive_category
from tests.integration.endpoints.types import AuthenticatedUser, CategoryData

API_CATEGORIES = "/api/v1/categories"
API_AUTH_REGISTER = "/api/v1/auth/register"
API_AUTH_LOGIN = "/api/v1/auth/login"


class TestCreateCategory:
    async def test_create_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload()

        response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()

        assert body["name"] == payload["name"]
        assert body["archived_at"] is None
        assert body["created_at"] is not None
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert "id" in body

    @pytest.mark.parametrize(
        "name, reason",
        [
            ("a", "min_length_allowed"),
            ("a" * 100, "max_length_allowed"),
            ("Food & Drinks", "special_chars_allowed"),
            ("Home Bills", "spaces_allowed"),
        ],
    )
    async def test_create_category_valid_names(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        name: str,
        reason: str,
    ):
        response = await client.post(
            API_CATEGORIES,
            json=category_payload(name),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_201_CREATED, reason
        assert response.json()["name"] == name

    async def test_create_category_duplicate_name(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload()

        create_response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert create_response.status_code == status.HTTP_201_CREATED

        response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_category_with_archived_name_conflicts(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        archived_category: CategoryData,
    ):
        payload = category_payload(archived_category["name"])

        response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "detail" in response.json()

    async def test_create_category_same_name_allowed_for_other_user(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload()

        first_response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )
        assert first_response.status_code == status.HTTP_201_CREATED

        assert first_response.json()["user_id"] == authenticated_user["user"]["id"]

        second_response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=other_authenticated_user["headers"],
        )
        assert second_response.status_code == status.HTTP_201_CREATED

        assert second_response.json()["user_id"] == other_authenticated_user["user"]["id"]

    @pytest.mark.parametrize(
        "payload, reason",
        [
            (category_payload(""), "empty_name"),
            (category_payload(" "), "blank_after_trim"),
            (category_payload("a" * 101), "too_long"),
            ({}, "missing_name"),
        ],
    )
    async def test_create_category_validation_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        payload: dict[str, str],
        reason: str,
    ):
        response = await client.post(
            API_CATEGORIES,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    async def test_create_category_without_token(self, client: AsyncClient):
        response = await client.post(
            API_CATEGORIES,
            json=category_payload(),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()


class TestGetCategories:
    async def test_get_categories_empty(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(API_CATEGORIES, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK

        assert response.json() == []

    async def test_get_categories_default_returns_active_categories(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        first_payload = category_payload("Food")

        second_payload = category_payload("Salary")

        await create_category(client, first_payload, authenticated_user["headers"])

        await create_category(client, second_payload, authenticated_user["headers"])

        response = await client.get(API_CATEGORIES, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK

        user_categories = response.json()

        category_names = {cat["name"] for cat in user_categories}

        assert len(category_names) == 2

        assert first_payload["name"] in category_names
        assert second_payload["name"] in category_names

        assert all(cat["archived_at"] is None for cat in user_categories)

    async def test_get_categories_returns_only_own_categories(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload()

        await create_category(client, payload, other_authenticated_user["headers"])
        await create_category(client, payload, authenticated_user["headers"])

        response = await client.get(API_CATEGORIES, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK

        user_categories = response.json()

        assert len(user_categories) == 1

        assert user_categories[0]["name"] == payload["name"]
        assert user_categories[0]["user_id"] == authenticated_user["user"]["id"]

    async def test_get_categories_category_status_archived_returns_archived_categories(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload()

        category = await create_category(client, payload, authenticated_user["headers"])

        await archive_category(client, category["id"], authenticated_user["headers"])

        response = await client.get(
            API_CATEGORIES,
            headers=authenticated_user["headers"],
            params={"category_status": "archived"},
        )

        assert response.status_code == status.HTTP_200_OK

        user_categories = response.json()

        assert len(user_categories) == 1
        assert user_categories[0]["name"] == payload["name"]
        assert user_categories[0]["user_id"] == authenticated_user["user"]["id"]
        assert user_categories[0]["archived_at"] is not None

    async def test_get_categories_category_status_all_returns_active_and_archived_categories(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        active_category_payload = category_payload()

        await create_category(client, active_category_payload, authenticated_user["headers"])

        archived_category_payload = category_payload("Salary")

        category = await create_category(
            client, archived_category_payload, authenticated_user["headers"]
        )

        await archive_category(client, category["id"], authenticated_user["headers"])

        response = await client.get(
            API_CATEGORIES, headers=authenticated_user["headers"], params={"category_status": "all"}
        )

        assert response.status_code == status.HTTP_200_OK

        user_categories = response.json()

        user_categories_names = {cat["name"] for cat in user_categories}

        assert len(user_categories_names) == 2

        assert active_category_payload["name"] in user_categories_names
        assert archived_category_payload["name"] in user_categories_names

        assert any(cat["archived_at"] is None for cat in user_categories)
        assert any(cat["archived_at"] is not None for cat in user_categories)

    async def test_get_categories_invalid_category_status(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.get(
            API_CATEGORIES,
            headers=authenticated_user["headers"],
            params={"category_status": "wrong_status"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        assert "detail" in response.json()

    async def test_get_categories_without_token(
        self,
        client: AsyncClient,
    ):
        response = await client.get(API_CATEGORIES)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestUpdateCategory:
    async def test_update_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        payload = category_payload("Salary")

        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["id"] == created_category["id"]
        assert body["name"] == payload["name"]
        assert body["user_id"] == authenticated_user["user"]["id"]
        assert body["archived_at"] is None

    @pytest.mark.parametrize(
        "name, reason",
        [
            ("a", "min_length_allowed"),
            ("a" * 100, "max_length_allowed"),
            ("Food & Drinks", "special_chars_allowed"),
            ("Home Bills", "spaces_allowed"),
        ],
    )
    async def test_update_category_valid_names(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        name: str,
        reason: str,
    ):
        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}",
            json=category_payload(name),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK, reason
        assert response.json()["name"] == name

    async def test_update_category_same_name_allowed(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}",
            json=category_payload(created_category["name"]),
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        assert response.json()["name"] == created_category["name"]

    @pytest.mark.parametrize(
        "payload, reason",
        [
            (category_payload(""), "empty_name"),
            (category_payload(" "), "blank_after_trim"),
            (category_payload("a" * 101), "too_long"),
            ({}, "missing_name"),
        ],
    )
    async def test_update_category_validation_fails(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
        payload: dict[str, str],
        reason: str,
    ):
        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason
        assert "detail" in response.json()

    async def test_update_category_duplicate_name(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        payload = category_payload("Salary")

        await create_category(client, payload, authenticated_user["headers"])

        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}",
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_update_category_of_other_user_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        payload = category_payload("Salary")

        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}",
            json=payload,
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_update_category_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload("Salary")

        response = await client.put(
            f"{API_CATEGORIES}/999", json=payload, headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_update_category_without_token(
        self,
        client: AsyncClient,
        created_category: CategoryData,
    ):
        response = await client.put(
            f"{API_CATEGORIES}/{created_category['id']}", json=category_payload()
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestArchiveCategory:
    async def test_archive_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        response = await client.delete(
            f"{API_CATEGORIES}/{created_category['id']}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        assert response.content == b""

        user_categories_response = await client.get(
            API_CATEGORIES, headers=authenticated_user["headers"]
        )

        assert user_categories_response.status_code == status.HTTP_200_OK

        assert user_categories_response.json() == []

        archived_response = await client.get(
            API_CATEGORIES,
            headers=authenticated_user["headers"],
            params={"category_status": "archived"},
        )

        assert archived_response.status_code == status.HTTP_200_OK

        archived_categories = archived_response.json()

        assert len(archived_categories) == 1
        assert archived_categories[0]["id"] == created_category["id"]
        assert archived_categories[0]["archived_at"] is not None

    async def test_archive_category_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(
            f"{API_CATEGORIES}/999", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_archive_category_of_other_user_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        response = await client.delete(
            f"{API_CATEGORIES}/{created_category['id']}",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_archive_category_already_archived(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        response = await client.delete(
            f"{API_CATEGORIES}/{created_category['id']}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        response = await client.delete(
            f"{API_CATEGORIES}/{created_category['id']}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_archive_category_without_token(
        self,
        client: AsyncClient,
        created_category: CategoryData,
    ):
        response = await client.delete(
            f"{API_CATEGORIES}/{created_category['id']}",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestRestoreCategory:
    async def test_restore_category_success(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        archived_category: CategoryData,
    ):
        response = await client.post(
            f"{API_CATEGORIES}/{archived_category['id']}/restore",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["id"] == archived_category["id"]
        assert body["name"] == archived_category["name"]
        assert body["user_id"] == archived_category["user_id"]
        assert body["archived_at"] is None

        archived_response = await client.get(
            API_CATEGORIES,
            headers=authenticated_user["headers"],
            params={"category_status": "archived"},
        )

        assert archived_response.status_code == status.HTTP_200_OK

        assert archived_response.json() == []

        user_categories_response = await client.get(
            API_CATEGORIES,
            headers=authenticated_user["headers"],
        )

        assert user_categories_response.status_code == status.HTTP_200_OK

        active_categories = user_categories_response.json()

        assert len(active_categories) == 1
        assert active_categories[0]["id"] == archived_category["id"]
        assert active_categories[0]["name"] == archived_category["name"]
        assert active_categories[0]["archived_at"] is None

    async def test_restore_category_not_found(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        response = await client.post(
            f"{API_CATEGORIES}/999/restore", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        assert "detail" in response.json()

    async def test_restore_category_of_other_user_forbidden(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
        archived_category: CategoryData,
    ):
        response = await client.post(
            f"{API_CATEGORIES}/{archived_category['id']}/restore",
            headers=other_authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

        assert "detail" in response.json()

    async def test_restore_category_not_archived(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        created_category: CategoryData,
    ):
        response = await client.post(
            f"{API_CATEGORIES}/{created_category['id']}/restore",
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    async def test_restore_category_without_token(
        self,
        client: AsyncClient,
        archived_category: CategoryData,
    ):
        response = await client.post(
            f"{API_CATEGORIES}/{archived_category['id']}/restore",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

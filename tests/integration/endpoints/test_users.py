import pytest

from fastapi import status
from httpx import AsyncClient

from tests.integration.endpoints.types import AuthenticatedUser

API_USERS_ME = "/api/v1/users/me"
API_USERS_ME_UPDATE_USERNAME = "/api/v1/users/me/username"
API_USERS_ME_UPDATE_PASSWORD = "/api/v1/users/me/password"


class TestGetMe:
    async def test_get_me_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        response = await client.get(
            API_USERS_ME,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["email"] == authenticated_user["user"]["email"]
        assert body["username"] == authenticated_user["user"]["username"]
        assert "id" in body
        assert "hashed_password" not in body
        assert "password" not in body

    async def test_get_me_without_token(
            self,
            client: AsyncClient
    ):
        response = await client.get(
            API_USERS_ME,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestUpdateUsername:
    async def test_update_username_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        payload = {"new_username": "newusername"}

        response = await client.put(
            API_USERS_ME_UPDATE_USERNAME,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["username"] == payload["new_username"]
        assert body["email"] == authenticated_user["user"]["email"]
        assert "hashed_password" not in body
        assert "password" not in body

        me_response = await client.get(
            API_USERS_ME,
            headers=authenticated_user["headers"],
        )

        assert me_response.status_code == status.HTTP_200_OK

        assert me_response.json()["username"] == payload["new_username"]

    async def test_update_username_duplicate(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        payload = {
            "new_username": "takenusername",
        }
        register_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@test.com",
                "username": payload["new_username"],
                "password": "Password123",
            })

        assert register_response.status_code == status.HTTP_201_CREATED

        response = await client.put(
            API_USERS_ME_UPDATE_USERNAME,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert "detail" in response.json()

    @pytest.mark.parametrize("payload, reason", [
        ({"new_username": "ab"}, "too_short"),
        ({"new_username": "a" * 55}, "too_long"),
        ({"new_username": "user name"}, "contains_space"),
        ({"new_username": "user@name"}, "special_chars"),
        ({}, "missing_new_username"),
    ])
    async def test_update_username_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            payload: dict[str, str],
            reason: str,
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_USERNAME,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

        assert "detail" in response.json()

    async def test_update_username_without_token(
            self,
            client: AsyncClient,
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_USERNAME,
            json={"new_username": "newusername"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

    async def test_update_username_same_as_current(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_USERNAME,
            json={"new_username": authenticated_user["user"]["username"]},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()

        assert body["username"] == authenticated_user["user"]["username"]
        assert body["email"] == authenticated_user["user"]["email"]
        assert "password" not in body
        assert "hashed_password" not in body


class TestUpdatePassword:
    async def test_update_password_success(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        payload = {
            "current_password": authenticated_user["user"]["password"],
            "new_password": "New" + authenticated_user["user"]["password"],
        }

        response = await client.put(
            API_USERS_ME_UPDATE_PASSWORD,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

        login_response = await client.post("/api/v1/auth/login", json={
            "email": authenticated_user["user"]["email"],
            "password": payload["new_password"],
        })
        assert login_response.status_code == status.HTTP_200_OK
        assert "access_token" in login_response.json()

        old_login = await client.post("/api/v1/auth/login", json={
            "email": authenticated_user["user"]["email"],
            "password": authenticated_user["user"]["password"],
        })

        assert old_login.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_password_wrong_current_password(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_PASSWORD,
            json={
                "current_password": "WrongPassword123",
                "new_password": "NewPassword1234",
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

    async def test_update_password_same_as_current(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_PASSWORD,
            json={
                "current_password": authenticated_user["user"]["password"],
                "new_password": authenticated_user["user"]["password"]
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

        assert "detail" in response.json()

    @pytest.mark.parametrize("payload, reason", [
        (
                {
                    "current_password": "Password123",
                    "new_password": "short",
                },
                "new_password_too_weak",
        ),
        (
                {
                    "new_password": "NewPassword123",
                },
                "missing_current_password",
        ),
        (
                {
                    "current_password": "Password123",
                },
                "missing_new_password",
        ),
    ])
    async def test_update_password_validation_fails(
            self,
            client: AsyncClient,
            authenticated_user: AuthenticatedUser,
            payload: dict[str, str],
            reason: str,
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_PASSWORD,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

        assert "detail" in response.json()

    async def test_update_password_without_token(
            self,
            client: AsyncClient,
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_PASSWORD,
            json={
                "current_password": "Password123",
                "new_password": "NewUsername123"
            }
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

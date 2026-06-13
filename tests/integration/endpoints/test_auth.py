import pytest
from fastapi import status
from httpx import AsyncClient

from tests.integration.endpoints.helpers import register_payload

API_AUTH_REGISTER_URL = "/api/v1/auth/register"

API_AUTH_LOGIN_URL = "/api/v1/auth/login"


class TestRegister:
    async def test_register_success(
            self,
            client: AsyncClient,
    ):
        payload = register_payload()

        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_201_CREATED

        body = response.json()
        assert body["email"] == payload["email"]
        assert body["username"] == payload["username"]
        assert "id" in body
        assert "hashed_password" not in body
        assert "password" not in body

    @pytest.mark.parametrize("payload, duplicate, reason", [
        (
                register_payload(),
                register_payload(username="otheruser"),
                "duplicate_email",
        ),
        (
                register_payload(),
                register_payload(email="seconduser@test.com"),
                "duplicate_username"
        )
    ])
    async def test_register_duplicate_value(
            self,
            client: AsyncClient,
            payload: dict[str, str],
            duplicate: dict[str, str],
            reason: str
    ):
        await client.post(API_AUTH_REGISTER_URL, json=payload)

        response = await client.post(API_AUTH_REGISTER_URL, json=duplicate)

        assert response.status_code == status.HTTP_409_CONFLICT, reason
        assert "detail" in response.json()

    @pytest.mark.parametrize("payload, reason", [
        (
                register_payload(email="invalid-email"),
                "invalid_email",
        ),
        (
                register_payload(username="t"),
                "username_too_short",
        ),
        (
                register_payload(username="t" * 55),
                "username_too_long",
        ),
        (
                register_payload(password="short"),
                "weak_password",
        ),
        (
                {
                    "email": "test@test.com",
                    "username": "testuser",
                },
                "missing_password",
        )
    ])
    async def test_register_validation_fails(
            self,
            client: AsyncClient,
            payload: dict[str, str],
            reason: str
    ):
        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

        assert "detail" in response.json()


class TestLogin:
    async def test_login_success(
            self,
            client: AsyncClient,
            registered_user: dict[str, str],
    ):
        response = await client.post(API_AUTH_LOGIN_URL, json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        })

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(
            self,
            client: AsyncClient,
            registered_user: dict[str, str],
    ):
        invalid_credentials = {
            "email": registered_user["email"],
            "password": "WrongPassword123",
        }

        response = await client.post(API_AUTH_LOGIN_URL, json=invalid_credentials)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

    async def test_login_unknown_email(
            self,
            client: AsyncClient,
            registered_user: dict[str, str],
    ):
        invalid_credentials = {
            "email": "unknownemail@test.com",
            "password": registered_user["password"],
        }

        response = await client.post(API_AUTH_LOGIN_URL, json=invalid_credentials)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "detail" in response.json()

    @pytest.mark.parametrize("payload, reason", [
        (
                {
                    "email": "invalid-email",
                    "password": "Password123",
                },
                "invalid_email",
        ),
        (
                {
                    "email": "user@test.com",
                },
                "missing_password",
        ),
        (
                {
                    "password": "Password123",
                },
                "missing_email",
        ),
    ])
    async def test_login_validation_fails(
            self,
            client: AsyncClient,
            payload: dict[str, str],
            reason: str
    ):
        response = await client.post(API_AUTH_LOGIN_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

        assert "detail" in response.json()

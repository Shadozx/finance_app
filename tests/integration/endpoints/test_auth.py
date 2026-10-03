import uuid
from datetime import timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import create_access_token, utc_now, verify_token
from app.core.error_codes import ErrorCode, FieldErrorCode
from app.models import UserSession
from app.services.default_categories import DEFAULT_CATEGORIES
from tests.integration.endpoints.helpers import (
    assert_field_error,
    assert_no_field_errors,
    assert_validation_error,
    register_payload,
    session_id_from_headers,
)
from tests.integration.endpoints.types import AuthenticatedUser, UserData

API_AUTH_REGISTER_URL = "/api/v1/auth/register"

API_AUTH_LOGIN_URL = "/api/v1/auth/login"

API_CATEGORIES_URL = "/api/v1/categories"

API_USERS_ME_URL = "/api/v1/users/me"

SESSION_TIME_OFFSET = timedelta(days=1)


class TestRegister:
    @pytest.mark.parametrize(
        "payload, code, field",
        [
            (register_payload(username="ab"), FieldErrorCode.STRING_TOO_SHORT, "username"),
            (register_payload(username="a" * 51), FieldErrorCode.STRING_TOO_LONG, "username"),
            (
                register_payload(username="invalid name"),
                FieldErrorCode.STRING_PATTERN_MISMATCH,
                "username",
            ),
            (
                register_payload(password="PasswordWithoutDigit"),
                FieldErrorCode.PASSWORD_TOO_WEAK,
                "password",
            ),
            (
                register_payload(password="12345678"),
                FieldErrorCode.PASSWORD_TOO_WEAK,
                "password",
            ),
        ],
    )
    async def test_register_named_validation_codes(
        self,
        client: AsyncClient,
        payload: dict[str, str],
        code: FieldErrorCode,
        field: str,
    ):
        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", field], code)
        assert "Value error," not in response.text

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

    async def test_register_creates_default_categories(self, client: AsyncClient):
        payload = register_payload()
        expected_categories = {
            (name, category_type.value) for name, category_type in DEFAULT_CATEGORIES
        }

        register_response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert register_response.status_code == status.HTTP_201_CREATED

        user_id = register_response.json()["id"]

        login_response = await client.post(
            API_AUTH_LOGIN_URL,
            json={"email": payload["email"], "password": payload["password"]},
        )

        assert login_response.status_code == status.HTTP_200_OK

        response = await client.get(
            API_CATEGORIES_URL,
            headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
        )

        assert response.status_code == status.HTTP_200_OK

        categories = response.json()["items"]

        assert len(categories) == len(expected_categories)
        assert {
            (category["name"], category["type"]) for category in categories
        } == expected_categories
        assert all(category["user_id"] == user_id for category in categories)
        assert all(category["archived_at"] is None for category in categories)

    @pytest.mark.parametrize(
        "payload, duplicate, reason",
        [
            (
                register_payload(),
                register_payload(username="otheruser"),
                "duplicate_email",
            ),
            (
                register_payload(),
                register_payload(email="seconduser@test.com"),
                "duplicate_username",
            ),
        ],
    )
    async def test_register_duplicate_value(
        self, client: AsyncClient, payload: dict[str, str], duplicate: dict[str, str], reason: str
    ):
        await client.post(API_AUTH_REGISTER_URL, json=payload)

        response = await client.post(API_AUTH_REGISTER_URL, json=duplicate)

        assert response.status_code == status.HTTP_409_CONFLICT, reason
        duplicate_field = next(
            field for field in ("email", "username") if duplicate[field] == payload[field]
        )
        assert_field_error(response, ErrorCode.ALREADY_EXISTS, ["body", duplicate_field])

    @pytest.mark.parametrize(
        "payload, reason",
        [
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
            ),
        ],
    )
    async def test_register_validation_fails(
        self, client: AsyncClient, payload: dict[str, str], reason: str
    ):
        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

        assert "detail" in response.json()


class TestLogin:
    async def test_login_success(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        registered_user: UserData,
    ):
        user_agent = "integration-test-agent"

        response = await client.post(
            API_AUTH_LOGIN_URL,
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
            headers={"User-Agent": user_agent},
        )

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

        payload = verify_token(body["access_token"])

        assert "sid" in payload

        session_id = uuid.UUID(payload["sid"])
        user_session = await test_session.scalar(
            select(UserSession).where(UserSession.id == session_id)
        )

        assert user_session is not None
        assert user_session.user_id == registered_user["id"]
        assert user_session.user_agent == user_agent

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

    @pytest.mark.parametrize(
        "payload, reason",
        [
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
        ],
    )
    async def test_login_validation_fails(
        self, client: AsyncClient, payload: dict[str, str], reason: str
    ):
        response = await client.post(API_AUTH_LOGIN_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, reason

        assert "detail" in response.json()


class TestSessionToken:
    async def test_get_me_rejects_token_without_sid(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        token = create_access_token({"sub": str(authenticated_user["user"]["id"])})

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_rejects_token_with_invalid_sid(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        invalid_session_id = "not-a-uuid"
        token = create_access_token(
            {"sub": str(authenticated_user["user"]["id"]), "sid": invalid_session_id}
        )

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_rejects_token_with_nonexistent_session(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        session_id = uuid.uuid4()
        token = create_access_token(
            {"sub": str(authenticated_user["user"]["id"]), "sid": str(session_id)}
        )

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_rejects_token_with_revoked_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
    ):
        active_response = await client.get(API_USERS_ME_URL, headers=authenticated_user["headers"])

        assert active_response.status_code == status.HTTP_200_OK

        session_id = session_id_from_headers(authenticated_user["headers"])
        revoked_at = utc_now()

        await test_session.execute(
            update(UserSession).where(UserSession.id == session_id).values(revoked_at=revoked_at)
        )

        response = await client.get(API_USERS_ME_URL, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_rejects_token_with_expired_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
    ):
        active_response = await client.get(API_USERS_ME_URL, headers=authenticated_user["headers"])

        assert active_response.status_code == status.HTTP_200_OK

        session_id = session_id_from_headers(authenticated_user["headers"])
        expires_at = utc_now() - SESSION_TIME_OFFSET

        await test_session.execute(
            update(UserSession).where(UserSession.id == session_id).values(expires_at=expires_at)
        )

        response = await client.get(API_USERS_ME_URL, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_rejects_token_with_another_users_session(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
    ):
        other_session_id = session_id_from_headers(other_authenticated_user["headers"])
        token = create_access_token(
            {"sub": str(authenticated_user["user"]["id"]), "sid": str(other_session_id)}
        )

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

import json
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from pytest_mock import MockerFixture
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.api.v1.endpoints.auth import REFRESH_REQUESTS_PER_MINUTE
from app.core import create_access_token, settings, utc_now, verify_token
from app.core.error_codes import ErrorCode, FieldErrorCode
from app.core.rate_limiter import limiter
from app.core.security import (
    create_refresh_token,
    hash_refresh_secret,
    parse_refresh_token,
    verify_refresh_token_signature,
)
from app.models import SessionRevocationReason, UserSession
from app.schemas.auth import REFRESH_TOKEN_MAX_LENGTH
from app.services.default_categories import DEFAULT_CATEGORIES
from tests.integration.endpoints.helpers import (
    OVER_MAX_PASSWORD,
    assert_field_error,
    assert_no_field_errors,
    assert_validation_error,
    forge_refresh_token,
    register_payload,
    session_id_from_headers,
)
from tests.integration.endpoints.types import AuthenticatedUser, UserData

API_AUTH_REGISTER_URL = "/api/v1/auth/register"

API_AUTH_LOGIN_URL = "/api/v1/auth/login"
API_AUTH_REFRESH_URL = "/api/v1/auth/refresh"
API_AUTH_LOGOUT_URL = "/api/v1/auth/logout"

API_CATEGORIES_URL = "/api/v1/categories"

API_USERS_ME_URL = "/api/v1/users/me"
API_USERS_ME_SESSIONS_URL = "/api/v1/users/me/sessions"

SESSION_TIME_OFFSET = timedelta(days=1)

# Valid for EmailStr, outside what the users table stores
NON_ASCII_EMAIL = "користувач@test.com"


@pytest.fixture
async def login_tokens(client: AsyncClient, registered_user: UserData) -> dict[str, str]:
    response = await client.post(
        API_AUTH_LOGIN_URL,
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()


@pytest.fixture
async def other_device_tokens(
    client: AsyncClient,
    registered_user: UserData,
    login_tokens: dict[str, str],
) -> dict[str, str]:
    response = await client.post(
        API_AUTH_LOGIN_URL,
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()


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
                register_payload(email=NON_ASCII_EMAIL),
                FieldErrorCode.INVALID_FORMAT,
                "email",
            ),
            (
                register_payload(password=OVER_MAX_PASSWORD),
                FieldErrorCode.STRING_TOO_LONG,
                "password",
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

    async def test_register_duplicate_email_ignores_case(self, client: AsyncClient):
        payload = register_payload()
        duplicate = register_payload(email=payload["email"].upper(), username="otheruser")

        await client.post(API_AUTH_REGISTER_URL, json=payload)

        response = await client.post(API_AUTH_REGISTER_URL, json=duplicate)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert_field_error(response, ErrorCode.ALREADY_EXISTS, ["body", "email"])

    async def test_register_lowercases_email(self, client: AsyncClient):
        payload = register_payload(email="User@Test.com")

        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["email"] == payload["email"].lower()

    async def test_register_accepts_email_with_apostrophe(self, client: AsyncClient):
        """EmailStr accepts it, so the model must store it rather than fail with a 500."""
        payload = register_payload(email="o'connor@test.com")

        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["email"] == payload["email"]

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
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert response.headers["Cache-Control"] == "no-store"

        payload = verify_token(body["access_token"])

        assert "sid" in payload

        session_id = uuid.UUID(payload["sid"])
        user_session = await test_session.scalar(
            select(UserSession).where(UserSession.id == session_id)
        )

        assert user_session is not None
        assert user_session.user_id == registered_user["id"]
        assert user_session.user_agent == user_agent
        parsed_token = parse_refresh_token(body["refresh_token"])
        assert parsed_token is not None
        refresh_session_id, secret, signature = parsed_token
        assert refresh_session_id == session_id
        assert verify_refresh_token_signature(refresh_session_id, secret, signature)
        assert user_session.refresh_token_hash == hash_refresh_secret(secret)
        assert user_session.refresh_token_hash != secret

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

    async def test_login_ignores_email_case(
        self,
        client: AsyncClient,
        registered_user: UserData,
    ):
        response = await client.post(
            API_AUTH_LOGIN_URL,
            json={
                "email": registered_user["email"].upper(),
                "password": registered_user["password"],
            },
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_login_treats_non_ascii_email_as_unknown(
        self,
        client: AsyncClient,
        registered_user: UserData,
    ):
        """Login only normalizes: an address registration would reject is simply unknown."""
        response = await client.post(
            API_AUTH_LOGIN_URL,
            json={"email": NON_ASCII_EMAIL, "password": registered_user["password"]},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_login_rejects_too_long_password(
        self,
        client: AsyncClient,
        registered_user: UserData,
    ):
        """Rejected by the schema, before any Argon2 run: 422, not 401."""
        response = await client.post(
            API_AUTH_LOGIN_URL,
            json={"email": registered_user["email"], "password": OVER_MAX_PASSWORD},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", "password"], FieldErrorCode.STRING_TOO_LONG)

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


class TestRefresh:
    async def test_refresh_rotates_tokens(
        self,
        client: AsyncClient,
        login_tokens: dict[str, str],
    ):
        response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["Cache-Control"] == "no-store"
        tokens = response.json()
        assert tokens["token_type"] == "bearer"
        assert tokens["refresh_token"] != login_tokens["refresh_token"]
        assert tokens["access_token"] != login_tokens["access_token"]

        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_200_OK

        next_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
        )
        assert next_refresh_response.status_code == status.HTTP_200_OK
        assert next_refresh_response.json()["refresh_token"] != tokens["refresh_token"]

    async def test_refresh_reuse_outside_grace_revokes_all_session_tokens(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert response.status_code == status.HTTP_200_OK
        current_tokens = response.json()
        session_id = uuid.UUID(verify_token(current_tokens["access_token"])["sid"])
        grace_interval = timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
        rotated_at = utc_now() - grace_interval - SESSION_TIME_OFFSET
        await test_session.execute(
            update(UserSession).where(UserSession.id == session_id).values(rotated_at=rotated_at)
        )

        reuse_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert reuse_response.status_code == status.HTTP_401_UNAUTHORIZED
        current_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": current_tokens["refresh_token"]}
        )
        assert current_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        for tokens in (login_tokens, current_tokens):
            access_response = await client.get(
                API_USERS_ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            assert access_response.status_code == status.HTTP_401_UNAUTHORIZED
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == session_id)
        )
        assert revoked_reason == SessionRevocationReason.REUSE_DETECTED

    async def test_refresh_token_two_generations_old_revokes_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        first_refresh_token = login_tokens["refresh_token"]
        second_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": first_refresh_token}
        )
        assert second_response.status_code == status.HTTP_200_OK
        second_tokens = second_response.json()
        third_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": second_tokens["refresh_token"]}
        )
        assert third_response.status_code == status.HTTP_200_OK
        third_tokens = third_response.json()
        session_id = uuid.UUID(verify_token(third_tokens["access_token"])["sid"])
        parsed_token = parse_refresh_token(first_refresh_token)
        assert parsed_token is not None
        assert verify_refresh_token_signature(*parsed_token)

        reuse_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": first_refresh_token}
        )

        assert reuse_response.status_code == status.HTTP_401_UNAUTHORIZED
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == session_id)
        )
        assert revoked_reason == SessionRevocationReason.REUSE_DETECTED
        current_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": third_tokens["refresh_token"]}
        )
        assert current_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_previous_token_in_grace_returns_usable_pair_without_extending_window(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        payload = {"refresh_token": login_tokens["refresh_token"]}
        response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert response.status_code == status.HTTP_200_OK
        current_tokens = response.json()
        session_id = uuid.UUID(verify_token(current_tokens["access_token"])["sid"])
        rotation_query = select(
            UserSession.previous_refresh_token_hash, UserSession.rotated_at, UserSession.revoked_at
        ).where(UserSession.id == session_id)
        original_rotation = (await test_session.execute(rotation_query)).one()

        retry_response = await client.post(API_AUTH_REFRESH_URL, json=payload)

        assert retry_response.status_code == status.HTTP_200_OK
        assert retry_response.headers["Cache-Control"] == "no-store"
        retry_tokens = retry_response.json()
        assert retry_tokens["refresh_token"] != current_tokens["refresh_token"]
        assert retry_tokens["refresh_token"] != login_tokens["refresh_token"]
        preserved_rotation = (await test_session.execute(rotation_query)).one()
        assert (
            preserved_rotation.previous_refresh_token_hash
            == original_rotation.previous_refresh_token_hash
        )
        assert preserved_rotation.rotated_at == original_rotation.rotated_at
        assert preserved_rotation.revoked_at is None

        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {retry_tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_200_OK
        next_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": retry_tokens["refresh_token"]}
        )
        assert next_refresh_response.status_code == status.HTTP_200_OK

    async def test_refresh_displaced_current_token_after_grace_rotation_revokes_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        # A retry in the grace window displaces the pair issued by the first refresh, and
        # later use of that pair is treated as reuse. This is acceptable only if the client
        # serializes refresh calls with a mutex: then it retries only when the first
        # response never arrived, so it never holds the displaced pair. Without the mutex,
        # two parallel refreshes can leave the client with the displaced pair, and its next
        # refresh revokes the session.
        payload = {"refresh_token": login_tokens["refresh_token"]}
        response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert response.status_code == status.HTTP_200_OK
        displaced_tokens = response.json()
        retry_response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert retry_response.status_code == status.HTTP_200_OK
        current_tokens = retry_response.json()

        reuse_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": displaced_tokens["refresh_token"]}
        )

        assert reuse_response.status_code == status.HTTP_401_UNAUTHORIZED
        current_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": current_tokens["refresh_token"]}
        )
        assert current_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        session_id = uuid.UUID(verify_token(current_tokens["access_token"])["sid"])
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == session_id)
        )
        assert revoked_reason == SessionRevocationReason.REUSE_DETECTED

    @pytest.mark.parametrize("session_state", ["expired", "revoked", "unknown"])
    async def test_refresh_rejects_inactive_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        session_state: str,
    ):
        parsed_token = parse_refresh_token(login_tokens["refresh_token"])
        assert parsed_token is not None
        session_id, secret, _signature = parsed_token
        refresh_token = login_tokens["refresh_token"]
        if session_state == "unknown":
            refresh_token = create_refresh_token(uuid.uuid4(), secret)
        else:
            now = utc_now()
            changes = (
                {"expires_at": now - SESSION_TIME_OFFSET}
                if session_state == "expired"
                else {"revoked_at": now, "revoked_reason": SessionRevocationReason.LOGOUT}
            )
            await test_session.execute(
                update(UserSession).where(UserSession.id == session_id).values(**changes)
            )

        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_reuse_revokes_only_compromised_device(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        other_device_tokens: dict[str, str],
    ):
        response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert response.status_code == status.HTTP_200_OK
        rotated_tokens = response.json()
        compromised_session_id = uuid.UUID(verify_token(rotated_tokens["access_token"])["sid"])
        grace_interval = timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
        await test_session.execute(
            update(UserSession)
            .where(UserSession.id == compromised_session_id)
            .values(rotated_at=utc_now() - grace_interval - SESSION_TIME_OFFSET)
        )

        reuse_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert reuse_response.status_code == status.HTTP_401_UNAUTHORIZED
        for tokens in (login_tokens, rotated_tokens):
            access_response = await client.get(
                API_USERS_ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            assert access_response.status_code == status.HTTP_401_UNAUTHORIZED
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == compromised_session_id)
        )
        assert revoked_reason == SessionRevocationReason.REUSE_DETECTED
        other_headers = {"Authorization": f"Bearer {other_device_tokens['access_token']}"}
        other_session_id = session_id_from_headers(other_headers)
        other_state = (
            await test_session.execute(
                select(UserSession.revoked_at, UserSession.revoked_reason).where(
                    UserSession.id == other_session_id
                )
            )
        ).one()
        assert other_state.revoked_at is None
        assert other_state.revoked_reason is None
        other_access_response = await client.get(API_USERS_ME_URL, headers=other_headers)
        assert other_access_response.status_code == status.HTTP_200_OK
        other_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": other_device_tokens["refresh_token"]}
        )
        assert other_refresh_response.status_code == status.HTTP_200_OK

    async def test_refresh_rejects_access_token_without_revoking_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        headers = {"Authorization": f"Bearer {login_tokens['access_token']}"}
        session_id = session_id_from_headers(headers)

        response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["access_token"]}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        state = (
            await test_session.execute(
                select(UserSession.revoked_at, UserSession.revoked_reason).where(
                    UserSession.id == session_id
                )
            )
        ).one()
        assert state.revoked_at is None
        assert state.revoked_reason is None
        access_response = await client.get(API_USERS_ME_URL, headers=headers)
        assert access_response.status_code == status.HTTP_200_OK
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize(
        "signature", ["forged-signature", "підроблений-підпис"], ids=["ascii", "non-ascii"]
    )
    async def test_refresh_rejects_forged_token_without_revoking_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        signature: str,
    ):
        headers = {"Authorization": f"Bearer {login_tokens['access_token']}"}
        session_id = session_id_from_headers(headers)
        forged_secret = "forged-refresh-secret"
        forged_token = forge_refresh_token(session_id, forged_secret, signature)

        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": forged_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        state = (
            await test_session.execute(
                select(UserSession.revoked_at, UserSession.revoked_reason).where(
                    UserSession.id == session_id
                )
            )
        ).one()
        assert state.revoked_at is None
        assert state.revoked_reason is None
        access_response = await client.get(API_USERS_ME_URL, headers=headers)
        assert access_response.status_code == status.HTTP_200_OK
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK

    async def test_refresh_rejects_substituted_session_id_and_keeps_both_sessions_active(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        other_authenticated_user: AuthenticatedUser,
    ):
        other_user = other_authenticated_user["user"]
        other_login_response = await client.post(
            API_AUTH_LOGIN_URL,
            json={"email": other_user["email"], "password": other_user["password"]},
        )
        assert other_login_response.status_code == status.HTTP_200_OK
        other_tokens = other_login_response.json()
        other_headers = {"Authorization": f"Bearer {other_tokens['access_token']}"}
        other_session_id = session_id_from_headers(other_headers)
        parsed_token = parse_refresh_token(login_tokens["refresh_token"])
        assert parsed_token is not None
        session_id, secret, signature = parsed_token
        assert session_id != other_session_id
        forged_token = forge_refresh_token(other_session_id, secret, signature)

        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": forged_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        for tokens in (login_tokens, other_tokens):
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            active_session_id = session_id_from_headers(headers)
            state = (
                await test_session.execute(
                    select(UserSession.revoked_at, UserSession.revoked_reason).where(
                        UserSession.id == active_session_id
                    )
                )
            ).one()
            assert state.revoked_at is None
            assert state.revoked_reason is None
            access_response = await client.get(API_USERS_ME_URL, headers=headers)
            assert access_response.status_code == status.HTTP_200_OK
            refresh_response = await client.post(
                API_AUTH_REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
            )
            assert refresh_response.status_code == status.HTTP_200_OK

    async def test_refresh_moves_older_device_to_top_of_session_list(
        self,
        client: AsyncClient,
        login_tokens: dict[str, str],
        other_device_tokens: dict[str, str],
    ):
        older_headers = {"Authorization": f"Bearer {login_tokens['access_token']}"}
        newer_headers = {"Authorization": f"Bearer {other_device_tokens['access_token']}"}
        older_session_id = str(session_id_from_headers(older_headers))
        newer_session_id = str(session_id_from_headers(newer_headers))
        original_response = await client.get(API_USERS_ME_SESSIONS_URL, headers=older_headers)
        assert original_response.status_code == status.HTTP_200_OK
        original_items = original_response.json()["items"]
        assert [item["id"] for item in original_items] == [newer_session_id, older_session_id]

        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert refresh_response.status_code == status.HTTP_200_OK
        refreshed_tokens = refresh_response.json()
        refreshed_headers = {"Authorization": f"Bearer {refreshed_tokens['access_token']}"}
        response = await client.get(API_USERS_ME_SESSIONS_URL, headers=refreshed_headers)
        assert response.status_code == status.HTTP_200_OK
        items = response.json()["items"]
        assert [item["id"] for item in items] == [older_session_id, newer_session_id]
        assert [item["is_current"] for item in items] == [True, False]
        refreshed_last_used_at = datetime.fromisoformat(items[0]["last_used_at"])
        original_last_used_at = datetime.fromisoformat(original_items[1]["last_used_at"])
        assert refreshed_last_used_at > original_last_used_at

    async def test_refresh_rejects_previous_token_in_grace_after_session_revocation(
        self,
        mocker: MockerFixture,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        now = utc_now()
        mocker.patch("app.services.user_service.utc_now", return_value=now)
        response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert response.status_code == status.HTTP_200_OK
        rotated_tokens = response.json()
        headers = {"Authorization": f"Bearer {rotated_tokens['access_token']}"}
        session_id = session_id_from_headers(headers)
        rotation = (
            await test_session.execute(
                select(UserSession.previous_refresh_token_hash, UserSession.rotated_at).where(
                    UserSession.id == session_id
                )
            )
        ).one()
        parsed_token = parse_refresh_token(login_tokens["refresh_token"])
        assert parsed_token is not None
        assert rotation.previous_refresh_token_hash == hash_refresh_secret(parsed_token.secret)
        assert rotation.rotated_at == now

        revoke_response = await client.delete(
            f"{API_USERS_ME_SESSIONS_URL}/{session_id}", headers=headers
        )
        assert revoke_response.status_code == status.HTTP_204_NO_CONTENT
        previous_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert previous_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == session_id)
        )
        assert revoked_reason == SessionRevocationReason.REVOKED_BY_USER

    @pytest.mark.parametrize("refresh_token", ["malformed-token", "invalid-uuid.secret.signature"])
    async def test_refresh_rejects_malformed_token(self, client: AsyncClient, refresh_token: str):
        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        "payload, code",
        [
            ({}, FieldErrorCode.MISSING),
            ({"refresh_token": ""}, FieldErrorCode.STRING_TOO_SHORT),
            (
                {"refresh_token": "x" * (REFRESH_TOKEN_MAX_LENGTH + 1)},
                FieldErrorCode.STRING_TOO_LONG,
            ),
        ],
        ids=["missing-field", "empty", "too-long"],
    )
    async def test_refresh_validates_request(
        self, client: AsyncClient, payload: dict[str, str], code: FieldErrorCode
    ):
        response = await client.post(API_AUTH_REFRESH_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", "refresh_token"], code)

    async def test_refresh_rate_limit(self, mocker: MockerFixture, client: AsyncClient):
        invalid_token = "malformed-token"
        limiter.reset()
        mocker.patch.object(limiter, "enabled", True)

        try:
            for _ in range(REFRESH_REQUESTS_PER_MINUTE):
                response = await client.post(
                    API_AUTH_REFRESH_URL, json={"refresh_token": invalid_token}
                )
                assert response.status_code == status.HTTP_401_UNAUTHORIZED

            response = await client.post(
                API_AUTH_REFRESH_URL, json={"refresh_token": invalid_token}
            )
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        finally:
            limiter.reset()


class TestLogout:
    async def test_logout_immediately_rejects_access_and_refresh_tokens(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        payload = {"refresh_token": login_tokens["refresh_token"]}
        headers = {"Authorization": f"Bearer {login_tokens['access_token']}"}
        active_response = await client.get(API_USERS_ME_URL, headers=headers)
        assert active_response.status_code == status.HTTP_200_OK

        response = await client.post(API_AUTH_LOGOUT_URL, json=payload)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        session_id = uuid.UUID(verify_token(login_tokens["access_token"])["sid"])
        revocation_query = select(UserSession.revoked_at, UserSession.revoked_reason).where(
            UserSession.id == session_id
        )
        original_revocation = (await test_session.execute(revocation_query)).one()
        assert original_revocation.revoked_at is not None
        assert original_revocation.revoked_reason == SessionRevocationReason.LOGOUT
        refresh_response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        access_response = await client.get(API_USERS_ME_URL, headers=headers)
        assert access_response.status_code == status.HTTP_401_UNAUTHORIZED
        repeated_logout_response = await client.post(API_AUTH_LOGOUT_URL, json=payload)
        assert repeated_logout_response.status_code == status.HTTP_204_NO_CONTENT
        assert repeated_logout_response.content == b""
        assert (await test_session.execute(revocation_query)).one() == original_revocation

    @pytest.mark.parametrize(
        "refresh_token",
        [
            "malformed-token",
            "invalid-uuid.secret.signature",
            f"{uuid.uuid4()}..signature",
            create_refresh_token(uuid.uuid4(), "unknown-session-refresh-secret"),
        ],
        ids=["missing-separator", "invalid-uuid", "empty-secret", "unknown-session"],
    )
    async def test_logout_ignores_invalid_token(self, client: AsyncClient, refresh_token: str):
        response = await client.post(API_AUTH_LOGOUT_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

    @pytest.mark.parametrize(
        "payload, code",
        [
            ({}, FieldErrorCode.MISSING),
            ({"refresh_token": ""}, FieldErrorCode.STRING_TOO_SHORT),
            (
                {"refresh_token": "x" * (REFRESH_TOKEN_MAX_LENGTH + 1)},
                FieldErrorCode.STRING_TOO_LONG,
            ),
        ],
        ids=["missing-field", "empty", "too-long"],
    )
    async def test_logout_validates_request(
        self, client: AsyncClient, payload: dict[str, str], code: FieldErrorCode
    ):
        response = await client.post(API_AUTH_LOGOUT_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", "refresh_token"], code)

    async def test_logout_forged_token_does_not_revoke_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        headers = {"Authorization": f"Bearer {login_tokens['access_token']}"}
        session_id = session_id_from_headers(headers)
        forged_secret = "forged-refresh-secret"
        forged_signature = "forged-signature"
        forged_token = forge_refresh_token(session_id, forged_secret, forged_signature)

        response = await client.post(API_AUTH_LOGOUT_URL, json={"refresh_token": forged_token})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        state = (
            await test_session.execute(
                select(UserSession.revoked_at, UserSession.revoked_reason).where(
                    UserSession.id == session_id
                )
            )
        ).one()
        assert state.revoked_at is None
        assert state.revoked_reason is None
        access_response = await client.get(API_USERS_ME_URL, headers=headers)
        assert access_response.status_code == status.HTTP_200_OK
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK

    async def test_logout_wrong_secret_does_not_revoke_session(
        self,
        client: AsyncClient,
        login_tokens: dict[str, str],
    ):
        payload = verify_token(login_tokens["access_token"])
        session_id = uuid.UUID(payload["sid"])
        wrong_token = create_refresh_token(session_id, "wrong-refresh-secret")

        response = await client.post(API_AUTH_LOGOUT_URL, json={"refresh_token": wrong_token})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {login_tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_200_OK
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK

    async def test_logout_old_refresh_token_does_not_revoke_rotated_session(
        self,
        client: AsyncClient,
        login_tokens: dict[str, str],
    ):
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        current_tokens = refresh_response.json()

        response = await client.post(
            API_AUTH_LOGOUT_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        current_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": current_tokens["refresh_token"]}
        )
        assert current_refresh_response.status_code == status.HTTP_200_OK


class TestTokenLogging:
    async def test_authentication_does_not_log_tokens_or_refresh_secrets(
        self,
        client: AsyncClient,
        registered_user: UserData,
    ):
        unknown_secret = "unknown-session-refresh-secret"
        unknown_refresh_token = create_refresh_token(uuid.uuid4(), unknown_secret)
        wrong_secret = "wrong-session-refresh-secret"
        forged_secret = "forged-session-refresh-secret"
        forged_signature = "forged-refresh-signature"

        with capture_logs() as logs:
            login_response = await client.post(
                API_AUTH_LOGIN_URL,
                json={"email": registered_user["email"], "password": registered_user["password"]},
            )
            assert login_response.status_code == status.HTTP_200_OK
            initial_tokens = login_response.json()
            refresh_response = await client.post(
                API_AUTH_REFRESH_URL, json={"refresh_token": initial_tokens["refresh_token"]}
            )
            assert refresh_response.status_code == status.HTTP_200_OK
            rotated_tokens = refresh_response.json()
            failed_refresh_response = await client.post(
                API_AUTH_REFRESH_URL, json={"refresh_token": unknown_refresh_token}
            )
            assert failed_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
            session_id = uuid.UUID(verify_token(rotated_tokens["access_token"])["sid"])
            forged_refresh_token = forge_refresh_token(session_id, forged_secret, forged_signature)
            forged_refresh_response = await client.post(
                API_AUTH_REFRESH_URL, json={"refresh_token": forged_refresh_token}
            )
            assert forged_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
            wrong_refresh_token = create_refresh_token(session_id, wrong_secret)
            failed_logout_response = await client.post(
                API_AUTH_LOGOUT_URL, json={"refresh_token": wrong_refresh_token}
            )
            assert failed_logout_response.status_code == status.HTTP_204_NO_CONTENT
            logout_response = await client.post(
                API_AUTH_LOGOUT_URL, json={"refresh_token": rotated_tokens["refresh_token"]}
            )
            assert logout_response.status_code == status.HTTP_204_NO_CONTENT

            compromised_login_response = await client.post(
                API_AUTH_LOGIN_URL,
                json={"email": registered_user["email"], "password": registered_user["password"]},
            )
            assert compromised_login_response.status_code == status.HTTP_200_OK
            compromised_tokens = compromised_login_response.json()
            compromised_session_id = uuid.UUID(
                verify_token(compromised_tokens["access_token"])["sid"]
            )
            mismatched_refresh_token = create_refresh_token(compromised_session_id, wrong_secret)
            reuse_response = await client.post(
                API_AUTH_REFRESH_URL, json={"refresh_token": mismatched_refresh_token}
            )
            assert reuse_response.status_code == status.HTTP_401_UNAUTHORIZED

        expected_events = {
            "user_authenticate_success",
            "user_session_refresh_success",
            "refresh_token_rejected_session_not_found",
            "refresh_token_rejected_invalid_signature",
            "logout_ignored_stale_refresh_token",
            "user_logout_success",
            "refresh_token_reuse_detected",
        }
        assert expected_events.issubset({entry["event"] for entry in logs})
        sensitive_values = [
            unknown_refresh_token,
            unknown_secret,
            wrong_refresh_token,
            wrong_secret,
            mismatched_refresh_token,
            forged_refresh_token,
            forged_secret,
            forged_signature,
        ]
        for tokens in (initial_tokens, rotated_tokens, compromised_tokens):
            parsed_token = parse_refresh_token(tokens["refresh_token"])
            assert parsed_token is not None
            sensitive_values.extend(
                [
                    tokens["access_token"],
                    tokens["refresh_token"],
                    parsed_token.secret,
                    parsed_token.signature,
                ]
            )
        serialized_logs = json.dumps(logs, default=str)
        for sensitive_value in sensitive_values:
            assert sensitive_value not in serialized_logs


class TestSessionToken:
    async def test_get_me_rejects_refresh_token_as_bearer(
        self,
        client: AsyncClient,
        login_tokens: dict[str, str],
    ):
        response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {login_tokens['refresh_token']}"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        valid_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {login_tokens['access_token']}"}
        )
        assert valid_response.status_code == status.HTTP_200_OK

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
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(revoked_at=revoked_at, revoked_reason=SessionRevocationReason.LOGOUT)
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

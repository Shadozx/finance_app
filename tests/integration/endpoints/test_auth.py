import asyncio
import json
import uuid
from datetime import datetime, timedelta

import pytest
from argon2 import Parameters, PasswordHasher, extract_parameters, profiles
from argon2.low_level import ARGON2_VERSION
from fastapi import status
from httpx import AsyncClient
from pytest_mock import MockerFixture
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from app.api.v1.endpoints.auth import REFRESH_REQUESTS_PER_MINUTE
from app.core import create_access_token, settings, utc_now, verify_token
from app.core.error_codes import ErrorCode, FieldErrorCode
from app.core.rate_limiter import limiter
from app.core.security import (
    ARGON2_HASH_LENGTH_BYTES,
    ARGON2_MEMORY_COST_KIB,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LENGTH_BYTES,
    ARGON2_TIME_COST,
    ARGON2_TYPE,
    create_refresh_token,
    derive_refresh_secret,
    hash_refresh_secret,
    parse_refresh_token,
    password_hasher,
    verify_refresh_token_signature,
)
from app.models import (
    INITIAL_REFRESH_GENERATION,
    Category,
    SessionRevocationReason,
    User,
    UserSession,
)
from app.repositories import UserSessionRepository
from app.schemas.auth import REFRESH_TOKEN_MAX_LENGTH
from app.schemas.validators import MIN_PASSWORD_LENGTH
from app.services.default_categories import DEFAULT_CATEGORIES
from tests.integration.endpoints.helpers import (
    CONCURRENCY_TIMEOUT_SECONDS,
    OVER_MAX_PASSWORD,
    FirstCallGate,
    assert_field_error,
    assert_no_field_errors,
    assert_validation_error,
    count_checked_out_connections_while_held,
    forge_refresh_token,
    hold_argon2,
    register_payload,
    run_concurrently,
    run_second_behind_first,
    session_id_from_headers,
    store_outdated_password_hash,
)
from tests.integration.endpoints.types import AuthenticatedUser, UserData
from tests.jwt_helpers import (
    ISSUER_AUDIENCE_DEFECTS,
    ClaimsBreaker,
    encode_test_jwt,
    read_jwt_claims,
    without_claim,
)

API_AUTH_REGISTER_URL = "/api/v1/auth/register"

API_AUTH_LOGIN_URL = "/api/v1/auth/login"
API_AUTH_REFRESH_URL = "/api/v1/auth/refresh"
API_AUTH_LOGOUT_URL = "/api/v1/auth/logout"
API_USERS_ME_UPDATE_PASSWORD = "/api/v1/users/me/password"

API_CATEGORIES_URL = "/api/v1/categories"

API_USERS_ME_URL = "/api/v1/users/me"
API_USERS_ME_SESSIONS_URL = "/api/v1/users/me/sessions"

SESSION_TIME_OFFSET = timedelta(days=1)

# Valid for EmailStr, outside what the users table stores
NON_ASCII_EMAIL = "користувач@test.com"

ACCESS_TOKEN_CLAIMS = {"sub", "sid", "exp", "iat", "iss", "aud"}

# A secret of the kind issued before secrets were derived from the generation
LEGACY_RANDOM_SECRET = "legacy-random-secret"
PREVIOUS_RANDOM_SECRET = "previous-random-secret"

GENERATION_AFTER_ONE_REFRESH = INITIAL_REFRESH_GENERATION + 1
GENERATION_AFTER_TWO_REFRESHES = INITIAL_REFRESH_GENERATION + 2

# The second racing registration, differing from the default payload in the named fields
OTHER_EMAIL = "otheruser@test.com"
OTHER_USERNAME = "otheruser"


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
            pytest.param(
                register_payload(username="ab"),
                FieldErrorCode.STRING_TOO_SHORT,
                "username",
                id="username_too_short",
            ),
            pytest.param(
                register_payload(username="a" * 51),
                FieldErrorCode.STRING_TOO_LONG,
                "username",
                id="username_too_long",
            ),
            pytest.param(
                register_payload(username="invalid name"),
                FieldErrorCode.STRING_PATTERN_MISMATCH,
                "username",
                id="username_invalid_pattern",
            ),
            pytest.param(
                register_payload(email=NON_ASCII_EMAIL),
                FieldErrorCode.INVALID_FORMAT,
                "email",
                id="non_ascii_email",
            ),
            pytest.param(
                register_payload(password=OVER_MAX_PASSWORD),
                FieldErrorCode.STRING_TOO_LONG,
                "password",
                id="password_too_long",
            ),
            pytest.param(
                register_payload(password="a" * (MIN_PASSWORD_LENGTH - 1)),
                FieldErrorCode.STRING_TOO_SHORT,
                "password",
                id="password_too_short",
            ),
        ],
    )
    async def test_register_invalid_field_returns_field_error_code(
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

    async def test_register_succeeds(
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

    async def test_register_default_categories_appear_in_categories(self, client: AsyncClient):
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
        "payload, duplicate, field",
        [
            pytest.param(
                register_payload(),
                register_payload(username="otheruser"),
                "email",
                id="duplicate_email",
            ),
            pytest.param(
                register_payload(),
                register_payload(email="seconduser@test.com"),
                "username",
                id="duplicate_username",
            ),
        ],
    )
    async def test_register_duplicate_value_conflicts(
        self, client: AsyncClient, payload: dict[str, str], duplicate: dict[str, str], field: str
    ):
        await client.post(API_AUTH_REGISTER_URL, json=payload)

        response = await client.post(API_AUTH_REGISTER_URL, json=duplicate)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert_field_error(response, ErrorCode.ALREADY_EXISTS, ["body", field])

    async def test_register_duplicate_email_other_case_conflicts(self, client: AsyncClient):
        payload = register_payload()
        duplicate = register_payload(email=payload["email"].upper(), username="otheruser")

        await client.post(API_AUTH_REGISTER_URL, json=payload)

        response = await client.post(API_AUTH_REGISTER_URL, json=duplicate)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert_field_error(response, ErrorCode.ALREADY_EXISTS, ["body", "email"])

    @pytest.mark.parametrize(
        "duplicate",
        [
            pytest.param(register_payload(), id="both"),
            pytest.param(register_payload(username=OTHER_USERNAME), id="email"),
            pytest.param(register_payload(email=OTHER_EMAIL), id="username"),
        ],
    )
    async def test_register_concurrent_duplicates_conflict(
        self,
        independent_client: AsyncClient,
        independent_session_factory: async_sessionmaker[AsyncSession],
        mocker: MockerFixture,
        duplicate: dict[str, str],
    ):
        payload = register_payload()
        payloads = [payload, duplicate]
        participant_count = len(payloads)
        hashed_password = "hashed"
        barrier = asyncio.Barrier(participant_count)
        matching_users = or_(
            User.email.in_({item["email"] for item in payloads}),
            User.username.in_({item["username"] for item in payloads}),
        )

        async def hash_password(password: str) -> str:
            # Both requests must pass the real duplicate checks before either can insert.
            await asyncio.wait_for(barrier.wait(), timeout=CONCURRENCY_TIMEOUT_SECONDS)
            return hashed_password

        mock_hash = mocker.patch.object(password_hasher, "hash", side_effect=hash_password)

        responses = await run_concurrently(
            *(independent_client.post(API_AUTH_REGISTER_URL, json=item) for item in payloads)
        )

        expected_status_codes = [status.HTTP_201_CREATED, status.HTTP_409_CONFLICT]
        assert sorted(response.status_code for response in responses) == expected_status_codes
        assert mock_hash.await_count == participant_count
        conflict = next(
            response for response in responses if response.status_code == status.HTTP_409_CONFLICT
        )
        assert conflict.headers["content-type"] == "application/problem+json"
        assert conflict.json() == {
            "status": status.HTTP_409_CONFLICT,
            "code": ErrorCode.ALREADY_EXISTS,
            "detail": "Resource with these values already exists",
        }

        async with independent_session_factory() as session:
            created_user = (await session.scalars(select(User).where(matching_users))).one()
            success = next(
                response
                for response in responses
                if response.status_code == status.HTTP_201_CREATED
            )
            assert created_user.id == success.json()["id"]
            categories = (
                await session.scalars(select(Category).where(Category.user_id == created_user.id))
            ).all()
            assert len(categories) == len(DEFAULT_CATEGORIES)
            assert {(category.name, category.type) for category in categories} == set(
                DEFAULT_CATEGORIES
            )

    async def test_register_mixed_case_email_returns_lowercase(self, client: AsyncClient):
        payload = register_payload(email="User@Test.com")

        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["email"] == payload["email"].lower()

    async def test_register_email_with_apostrophe_allowed(self, client: AsyncClient):
        """EmailStr accepts it, so the model must store it rather than fail with a 500."""
        payload = register_payload(email="o'connor@test.com")

        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["email"] == payload["email"]

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(
                register_payload(email="invalid-email"),
                id="invalid_email",
            ),
            pytest.param(
                register_payload(username="t"),
                id="username_too_short",
            ),
            pytest.param(
                register_payload(username="t" * 55),
                id="username_too_long",
            ),
            pytest.param(
                register_payload(password="short"),
                id="short_password",
            ),
            pytest.param(
                {
                    "email": "test@test.com",
                    "username": "testuser",
                },
                id="missing_password",
            ),
        ],
    )
    async def test_register_invalid_payload_rejected(
        self, client: AsyncClient, payload: dict[str, str]
    ):
        response = await client.post(API_AUTH_REGISTER_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        assert "detail" in response.json()


class TestLogin:
    async def test_login_decomposed_password_succeeds(self, client: AsyncClient):
        composed_password = "LongPassword123\u0439"
        decomposed_password = "LongPassword123\u0438\u0306"
        payload = register_payload(password=composed_password)

        registration = await client.post(API_AUTH_REGISTER_URL, json=payload)
        assert registration.status_code == status.HTTP_201_CREATED

        response = await client.post(
            API_AUTH_LOGIN_URL,
            json={"email": payload["email"], "password": decomposed_password},
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_login_succeeds(
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

        assert type(body["expires_in"]) is int
        assert payload["exp"] - payload["iat"] == body["expires_in"]
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

    async def test_login_outdated_hash_updates_stored_hash(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        registered_user: UserData,
    ):
        outdated_parameters = profiles.CHEAPEST
        expected_parameters = Parameters(
            type=ARGON2_TYPE,
            version=ARGON2_VERSION,
            salt_len=ARGON2_SALT_LENGTH_BYTES,
            hash_len=ARGON2_HASH_LENGTH_BYTES,
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST_KIB,
            parallelism=ARGON2_PARALLELISM,
        )
        stored_user = await test_session.scalar(
            select(User).where(User.id == registered_user["id"])
        )
        assert stored_user is not None

        outdated_hash = PasswordHasher.from_parameters(outdated_parameters).hash(
            registered_user["password"]
        )
        stored_user.hashed_password = outdated_hash
        password_version = stored_user.password_version
        password_changed_at = stored_user.password_changed_at
        await test_session.commit()

        response = await client.post(
            API_AUTH_LOGIN_URL,
            json={
                "email": registered_user["email"],
                "password": registered_user["password"],
            },
        )

        assert response.status_code == status.HTTP_200_OK

        await test_session.refresh(stored_user)

        assert stored_user.hashed_password != outdated_hash
        assert extract_parameters(stored_user.hashed_password) == expected_parameters
        assert stored_user.password_version == password_version
        assert stored_user.password_changed_at == password_changed_at

    async def test_login_wrong_password_unauthorized(
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

    async def test_login_unknown_email_unauthorized(
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

    async def test_login_mixed_case_email_succeeds(
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

    async def test_login_non_ascii_email_unauthorized(
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

    async def test_login_too_long_password_rejected(
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
        "payload",
        [
            pytest.param(
                {
                    "email": "invalid-email",
                    "password": "Password123",
                },
                id="invalid_email",
            ),
            pytest.param(
                {
                    "email": "user@test.com",
                },
                id="missing_password",
            ),
            pytest.param(
                {
                    "password": "Password123",
                },
                id="missing_email",
            ),
        ],
    )
    async def test_login_invalid_payload_rejected(
        self, client: AsyncClient, payload: dict[str, str]
    ):
        response = await client.post(API_AUTH_LOGIN_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        assert "detail" in response.json()

    async def test_login_returns_access_token_with_only_expected_claims(
        self,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
    ):
        token = authenticated_user["headers"]["Authorization"].removeprefix("Bearer ")
        user_id = authenticated_user["user"]["id"]
        stored_session_id = (
            await test_session.scalars(select(UserSession.id).where(UserSession.user_id == user_id))
        ).one()

        claims = read_jwt_claims(token)

        assert set(claims) == ACCESS_TOKEN_CLAIMS
        assert claims["sub"] == str(user_id)
        assert claims["sid"] == str(stored_session_id)


class TestRefresh:
    async def test_refresh_returns_rotated_token_pair(
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

        payload = verify_token(tokens["access_token"])
        assert type(tokens["expires_in"]) is int
        assert payload["exp"] - payload["iat"] == tokens["expires_in"]

        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_200_OK

        next_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": tokens["refresh_token"]}
        )
        assert next_refresh_response.status_code == status.HTTP_200_OK
        assert next_refresh_response.json()["refresh_token"] != tokens["refresh_token"]

    async def test_refresh_reused_token_outside_grace_revokes_session(
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

    async def test_refresh_two_generations_old_token_revokes_session(
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

    async def test_refresh_previous_token_in_grace_returns_usable_pair(
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
        assert retry_tokens["refresh_token"] == current_tokens["refresh_token"]
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

    async def test_refresh_grace_replay_keeps_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        payload = {"refresh_token": login_tokens["refresh_token"]}
        response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert response.status_code == status.HTTP_200_OK
        first_tokens = response.json()
        retry_response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert retry_response.status_code == status.HTTP_200_OK
        retry_tokens = retry_response.json()
        assert retry_tokens["refresh_token"] == first_tokens["refresh_token"]

        next_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": first_tokens["refresh_token"]}
        )

        assert next_refresh_response.status_code == status.HTTP_200_OK
        session_id = uuid.UUID(verify_token(first_tokens["access_token"])["sid"])
        revoked_at = await test_session.scalar(
            select(UserSession.revoked_at).where(UserSession.id == session_id)
        )
        assert revoked_at is None

    async def test_refresh_grace_replay_with_random_secret_unauthorized(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        session_id = uuid.UUID(verify_token(login_tokens["access_token"])["sid"])
        await test_session.execute(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(
                refresh_token_hash=hash_refresh_secret(LEGACY_RANDOM_SECRET),
                previous_refresh_token_hash=hash_refresh_secret(PREVIOUS_RANDOM_SECRET),
                rotated_at=utc_now(),
            )
        )
        state_query = select(
            UserSession.refresh_token_hash,
            UserSession.previous_refresh_token_hash,
            UserSession.rotated_at,
            UserSession.refresh_generation,
            UserSession.last_used_at,
            UserSession.expires_at,
            UserSession.revoked_at,
        ).where(UserSession.id == session_id)
        original_state = (await test_session.execute(state_query)).one()

        with capture_logs() as logs:
            replay_response = await client.post(
                API_AUTH_REFRESH_URL,
                json={"refresh_token": create_refresh_token(session_id, PREVIOUS_RANDOM_SECRET)},
            )

        assert replay_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert (await test_session.execute(state_query)).one() == original_state
        assert [log for log in logs if log["event"] == "refresh_replay_unavailable"] == [
            {
                "event": "refresh_replay_unavailable",
                "session_id": str(session_id),
                "log_level": "warning",
            }
        ]
        current_response = await client.post(
            API_AUTH_REFRESH_URL,
            json={"refresh_token": create_refresh_token(session_id, LEGACY_RANDOM_SECRET)},
        )
        assert current_response.status_code == status.HTTP_200_OK

    async def test_refresh_unknown_session_unauthorized(
        self,
        client: AsyncClient,
    ):
        refresh_token = create_refresh_token(uuid.uuid4(), "unknown-session-refresh-secret")

        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_revoked_session_unauthorized(
        self,
        client: AsyncClient,
        login_tokens: dict[str, str],
    ):
        payload = {"refresh_token": login_tokens["refresh_token"]}
        logout_response = await client.post(API_AUTH_LOGOUT_URL, json=payload)
        assert logout_response.status_code == status.HTTP_204_NO_CONTENT

        response = await client.post(API_AUTH_REFRESH_URL, json=payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_expired_session_unauthorized(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        parsed_token = parse_refresh_token(login_tokens["refresh_token"])
        assert parsed_token is not None
        session_id = parsed_token.session_id
        refresh_token = login_tokens["refresh_token"]
        await test_session.execute(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(expires_at=utc_now() - SESSION_TIME_OFFSET)
        )

        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_reused_token_revokes_only_compromised_device(
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

    async def test_refresh_access_token_unauthorized(
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
        "signature",
        [
            pytest.param("forged-signature", id="ascii"),
            pytest.param("підроблений-підпис", id="non_ascii"),
        ],
    )
    async def test_refresh_forged_token_unauthorized(
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

    async def test_refresh_substituted_session_id_unauthorized(
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

    async def test_refresh_older_device_moves_to_top_of_sessions(
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

    async def test_refresh_previous_token_after_revocation_unauthorized(
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

    @pytest.mark.parametrize(
        "refresh_token",
        [
            pytest.param("malformed-token", id="malformed"),
            pytest.param("invalid-uuid.secret.signature", id="invalid_uuid"),
        ],
    )
    async def test_refresh_malformed_token_unauthorized(
        self, client: AsyncClient, refresh_token: str
    ):
        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize(
        "payload, code",
        [
            pytest.param({}, FieldErrorCode.MISSING, id="missing_field"),
            pytest.param({"refresh_token": ""}, FieldErrorCode.STRING_TOO_SHORT, id="empty"),
            pytest.param(
                {"refresh_token": "x" * (REFRESH_TOKEN_MAX_LENGTH + 1)},
                FieldErrorCode.STRING_TOO_LONG,
                id="too_long",
            ),
        ],
    )
    async def test_refresh_invalid_payload_rejected(
        self, client: AsyncClient, payload: dict[str, str], code: FieldErrorCode
    ):
        response = await client.post(API_AUTH_REFRESH_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", "refresh_token"], code)

    async def test_refresh_over_rate_limit_too_many_requests(
        self, mocker: MockerFixture, client: AsyncClient
    ):
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
    async def test_logout_access_and_refresh_tokens_unauthorized_after(
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
            pytest.param("malformed-token", id="missing_separator"),
            pytest.param("invalid-uuid.secret.signature", id="invalid_uuid"),
            pytest.param(f"{uuid.uuid4()}..signature", id="empty_secret"),
            pytest.param(
                create_refresh_token(uuid.uuid4(), "unknown-session-refresh-secret"),
                id="unknown_session",
            ),
        ],
    )
    async def test_logout_invalid_token_succeeds(self, client: AsyncClient, refresh_token: str):
        response = await client.post(API_AUTH_LOGOUT_URL, json={"refresh_token": refresh_token})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

    @pytest.mark.parametrize(
        "payload, code",
        [
            pytest.param({}, FieldErrorCode.MISSING, id="missing_field"),
            pytest.param({"refresh_token": ""}, FieldErrorCode.STRING_TOO_SHORT, id="empty"),
            pytest.param(
                {"refresh_token": "x" * (REFRESH_TOKEN_MAX_LENGTH + 1)},
                FieldErrorCode.STRING_TOO_LONG,
                id="too_long",
            ),
        ],
    )
    async def test_logout_invalid_payload_rejected(
        self, client: AsyncClient, payload: dict[str, str], code: FieldErrorCode
    ):
        response = await client.post(API_AUTH_LOGOUT_URL, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", "refresh_token"], code)

    async def test_logout_forged_token_keeps_session(
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

    async def test_logout_wrong_secret_revokes_session_as_reuse(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        payload = verify_token(login_tokens["access_token"])
        session_id = uuid.UUID(payload["sid"])
        wrong_token = create_refresh_token(session_id, "wrong-refresh-secret")
        reason_query = select(UserSession.revoked_reason).where(UserSession.id == session_id)

        response = await client.post(API_AUTH_LOGOUT_URL, json={"refresh_token": wrong_token})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert await test_session.scalar(reason_query) == SessionRevocationReason.REUSE_DETECTED
        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {login_tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_401_UNAUTHORIZED
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        repeated_logout_response = await client.post(
            API_AUTH_LOGOUT_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert repeated_logout_response.status_code == status.HTTP_204_NO_CONTENT
        assert await test_session.scalar(reason_query) == SessionRevocationReason.REUSE_DETECTED

    async def test_logout_previous_token_in_grace_revokes_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        current_tokens = refresh_response.json()
        session_id = uuid.UUID(verify_token(current_tokens["access_token"])["sid"])
        revocation_query = select(UserSession.revoked_at, UserSession.revoked_reason).where(
            UserSession.id == session_id
        )

        response = await client.post(
            API_AUTH_LOGOUT_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        revocation = (await test_session.execute(revocation_query)).one()
        assert revocation.revoked_at is not None
        assert revocation.revoked_reason == SessionRevocationReason.LOGOUT
        current_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": current_tokens["refresh_token"]}
        )
        assert current_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {current_tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_401_UNAUTHORIZED
        repeated_logout_response = await client.post(
            API_AUTH_LOGOUT_URL, json={"refresh_token": current_tokens["refresh_token"]}
        )
        assert repeated_logout_response.status_code == status.HTTP_204_NO_CONTENT
        assert (await test_session.execute(revocation_query)).one() == revocation

    async def test_logout_previous_token_outside_grace_revokes_session_as_reuse(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
    ):
        refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        current_tokens = refresh_response.json()
        session_id = uuid.UUID(verify_token(current_tokens["access_token"])["sid"])
        grace_interval = timedelta(seconds=settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS)
        rotated_at = utc_now() - grace_interval - SESSION_TIME_OFFSET
        await test_session.execute(
            update(UserSession).where(UserSession.id == session_id).values(rotated_at=rotated_at)
        )

        response = await client.post(
            API_AUTH_LOGOUT_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == session_id)
        )
        assert revoked_reason == SessionRevocationReason.REUSE_DETECTED
        current_refresh_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": current_tokens["refresh_token"]}
        )
        assert current_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        access_response = await client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {current_tokens['access_token']}"}
        )
        assert access_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRefreshGeneration:
    @pytest.fixture
    def session_id(self, login_tokens: dict[str, str]) -> uuid.UUID:
        return uuid.UUID(verify_token(login_tokens["access_token"])["sid"])

    # Reads the column, not the entity attribute
    async def stored_generation(self, test_session: AsyncSession, session_id: uuid.UUID) -> int:
        return (
            await test_session.scalars(
                select(UserSession.refresh_generation).where(UserSession.id == session_id)
            )
        ).one()

    async def test_login_sets_initial_generation(
        self, test_session: AsyncSession, session_id: uuid.UUID
    ):
        assert await self.stored_generation(test_session, session_id) == INITIAL_REFRESH_GENERATION

    async def test_login_returns_derived_secret_of_initial_generation(
        self, login_tokens: dict[str, str], session_id: uuid.UUID
    ):
        parsed_token = parse_refresh_token(login_tokens["refresh_token"])

        assert parsed_token is not None
        assert parsed_token.secret == derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION)

    async def test_refresh_random_secret_replaced_with_derived(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        session_id: uuid.UUID,
    ):
        assert LEGACY_RANDOM_SECRET != derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION)
        await test_session.execute(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(refresh_token_hash=hash_refresh_secret(LEGACY_RANDOM_SECRET))
        )
        legacy_token = create_refresh_token(session_id, LEGACY_RANDOM_SECRET)

        response = await client.post(API_AUTH_REFRESH_URL, json={"refresh_token": legacy_token})

        assert response.status_code == status.HTTP_200_OK
        parsed_token = parse_refresh_token(response.json()["refresh_token"])
        assert parsed_token is not None
        assert parsed_token.secret == derive_refresh_secret(
            session_id, GENERATION_AFTER_ONE_REFRESH
        )

    async def test_refresh_advances_generation(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        session_id: uuid.UUID,
    ):
        first_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        assert first_response.status_code == status.HTTP_200_OK
        assert (
            await self.stored_generation(test_session, session_id) == GENERATION_AFTER_ONE_REFRESH
        )

        second_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": first_response.json()["refresh_token"]}
        )

        assert second_response.status_code == status.HTTP_200_OK
        assert (
            await self.stored_generation(test_session, session_id) == GENERATION_AFTER_TWO_REFRESHES
        )

    async def test_refresh_in_grace_keeps_generation(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        session_id: uuid.UUID,
    ):
        payload = {"refresh_token": login_tokens["refresh_token"]}
        first_response = await client.post(API_AUTH_REFRESH_URL, json=payload)
        assert first_response.status_code == status.HTTP_200_OK

        retry_response = await client.post(API_AUTH_REFRESH_URL, json=payload)

        assert retry_response.status_code == status.HTTP_200_OK
        assert (
            await self.stored_generation(test_session, session_id) == GENERATION_AFTER_ONE_REFRESH
        )

    async def test_refresh_reused_token_keeps_generation(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        session_id: uuid.UUID,
    ):
        first_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )
        second_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": first_response.json()["refresh_token"]}
        )
        assert second_response.status_code == status.HTTP_200_OK
        assert (
            await self.stored_generation(test_session, session_id) == GENERATION_AFTER_TWO_REFRESHES
        )

        reuse_response = await client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert reuse_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert (
            await self.stored_generation(test_session, session_id) == GENERATION_AFTER_TWO_REFRESHES
        )
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == session_id)
        )
        assert revoked_reason == SessionRevocationReason.REUSE_DETECTED

    async def test_logout_keeps_generation(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        login_tokens: dict[str, str],
        session_id: uuid.UUID,
    ):
        response = await client.post(
            API_AUTH_LOGOUT_URL, json={"refresh_token": login_tokens["refresh_token"]}
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert await self.stored_generation(test_session, session_id) == INITIAL_REFRESH_GENERATION


class TestLoginConcurrency:
    async def test_login_concurrent_rehash_succeeds(
        self,
        independent_client: AsyncClient,
        independent_session_factory: async_sessionmaker[AsyncSession],
        independent_registered_user: UserData,
        held_user_update: FirstCallGate,
    ):
        await store_outdated_password_hash(independent_session_factory, independent_registered_user)
        payload = {
            "email": independent_registered_user["email"],
            "password": independent_registered_user["password"],
        }

        first_response, second_response = await run_second_behind_first(
            independent_client.post(API_AUTH_LOGIN_URL, json=payload),
            independent_client.post(API_AUTH_LOGIN_URL, json=payload),
            gate=held_user_update,
            session_factory=independent_session_factory,
        )

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_200_OK

    async def test_login_concurrent_password_change_unauthorized(
        self,
        independent_client: AsyncClient,
        independent_session_factory: async_sessionmaker[AsyncSession],
        independent_registered_user: UserData,
        independent_login_tokens: dict[str, str],
        held_user_update: FirstCallGate,
    ):
        await store_outdated_password_hash(independent_session_factory, independent_registered_user)
        new_password = "New" + independent_registered_user["password"]
        headers = {"Authorization": f"Bearer {independent_login_tokens['access_token']}"}
        login_payload = {
            "email": independent_registered_user["email"],
            "password": independent_registered_user["password"],
        }
        password_payload = {
            "current_password": independent_registered_user["password"],
            "new_password": new_password,
        }

        update_response, login_response = await run_second_behind_first(
            independent_client.put(
                API_USERS_ME_UPDATE_PASSWORD, json=password_payload, headers=headers
            ),
            independent_client.post(API_AUTH_LOGIN_URL, json=login_payload),
            gate=held_user_update,
            session_factory=independent_session_factory,
        )

        new_login = await independent_client.post(
            API_AUTH_LOGIN_URL, json={**login_payload, "password": new_password}
        )
        old_login = await independent_client.post(API_AUTH_LOGIN_URL, json=login_payload)

        assert update_response.status_code == status.HTTP_204_NO_CONTENT
        assert login_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert new_login.status_code == status.HTTP_200_OK
        assert old_login.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_login_during_argon2_connection_released(
        self,
        mocker: MockerFixture,
        test_engine: AsyncEngine,
        independent_client: AsyncClient,
        independent_registered_user: UserData,
    ):
        expected_checked_out_connections = 0
        gate = hold_argon2(mocker, "verify")

        response, checked_out_connections = await run_concurrently(
            independent_client.post(
                API_AUTH_LOGIN_URL,
                json={
                    "email": independent_registered_user["email"],
                    "password": independent_registered_user["password"],
                },
            ),
            count_checked_out_connections_while_held(gate, test_engine),
        )

        assert response.status_code == status.HTTP_200_OK
        assert checked_out_connections == expected_checked_out_connections


class TestRefreshConcurrency:
    @pytest.fixture
    def session_id(self, independent_login_tokens: dict[str, str]) -> uuid.UUID:
        return uuid.UUID(verify_token(independent_login_tokens["access_token"])["sid"])

    # Set up after the login, so that only the requests under test reach the held update. The
    # request that locks the session first reaches update first, and stays there until the
    # other one is queued behind its lock.
    @pytest.fixture
    def held_update(
        self, mocker: MockerFixture, independent_login_tokens: dict[str, str]
    ) -> FirstCallGate:
        # The window must not be shorter than the longest wait of the second request, or a slow
        # run would take its replay for a reuse and revoke the session
        mocker.patch(
            "app.services.user_service.settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS",
            CONCURRENCY_TIMEOUT_SECONDS,
        )
        gate = FirstCallGate()
        mocker.patch.object(
            UserSessionRepository,
            "update",
            autospec=True,
            side_effect=gate.wrap(UserSessionRepository.update),
        )

        return gate

    async def stored_session(
        self, session_factory: async_sessionmaker[AsyncSession], session_id: uuid.UUID
    ):
        async with session_factory() as session:
            return (
                await session.execute(
                    select(
                        UserSession.refresh_generation,
                        UserSession.revoked_at,
                        UserSession.revoked_reason,
                    ).where(UserSession.id == session_id)
                )
            ).one()

    async def test_refresh_concurrent_same_token_returns_same_successor(
        self,
        independent_client: AsyncClient,
        independent_session_factory: async_sessionmaker[AsyncSession],
        independent_login_tokens: dict[str, str],
        session_id: uuid.UUID,
        held_update: FirstCallGate,
    ):
        refresh_payload = {"refresh_token": independent_login_tokens["refresh_token"]}

        with capture_logs() as logs:
            first_response, second_response = await run_second_behind_first(
                independent_client.post(API_AUTH_REFRESH_URL, json=refresh_payload),
                independent_client.post(API_AUTH_REFRESH_URL, json=refresh_payload),
                gate=held_update,
                session_factory=independent_session_factory,
            )

        assert first_response.status_code == status.HTTP_200_OK
        assert second_response.status_code == status.HTTP_200_OK
        successor_token = first_response.json()["refresh_token"]
        assert second_response.json()["refresh_token"] == successor_token
        refresh_matches = sorted(
            log["match"] for log in logs if log["event"] == "user_session_refresh_success"
        )
        assert refresh_matches == ["current", "previous_in_grace"]
        stored_session = await self.stored_session(independent_session_factory, session_id)
        assert stored_session.refresh_generation == GENERATION_AFTER_ONE_REFRESH
        assert stored_session.revoked_at is None
        follow_up_response = await independent_client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": successor_token}
        )
        assert follow_up_response.status_code == status.HTTP_200_OK

    async def test_logout_old_token_after_concurrent_refresh_revokes_session(
        self,
        independent_client: AsyncClient,
        independent_session_factory: async_sessionmaker[AsyncSession],
        independent_login_tokens: dict[str, str],
        session_id: uuid.UUID,
        held_update: FirstCallGate,
    ):
        old_payload = {"refresh_token": independent_login_tokens["refresh_token"]}

        with capture_logs() as logs:
            refresh_response, logout_response = await run_second_behind_first(
                independent_client.post(API_AUTH_REFRESH_URL, json=old_payload),
                independent_client.post(API_AUTH_LOGOUT_URL, json=old_payload),
                gate=held_update,
                session_factory=independent_session_factory,
            )

        assert refresh_response.status_code == status.HTTP_200_OK
        assert logout_response.status_code == status.HTTP_204_NO_CONTENT
        new_tokens = refresh_response.json()
        stored_session = await self.stored_session(independent_session_factory, session_id)
        assert stored_session.revoked_reason == SessionRevocationReason.LOGOUT
        new_refresh_response = await independent_client.post(
            API_AUTH_REFRESH_URL, json={"refresh_token": new_tokens["refresh_token"]}
        )
        assert new_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        new_access_response = await independent_client.get(
            API_USERS_ME_URL, headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
        )
        assert new_access_response.status_code == status.HTTP_401_UNAUTHORIZED
        refresh_matches = [
            log["match"] for log in logs if log["event"] == "user_session_refresh_success"
        ]
        logout_matches = [log["match"] for log in logs if log["event"] == "user_logout_success"]
        assert refresh_matches == ["current"]
        assert logout_matches == ["previous_in_grace"]

    async def test_refresh_after_concurrent_logout_unauthorized(
        self,
        independent_client: AsyncClient,
        independent_session_factory: async_sessionmaker[AsyncSession],
        independent_login_tokens: dict[str, str],
        session_id: uuid.UUID,
        held_update: FirstCallGate,
    ):
        payload = {"refresh_token": independent_login_tokens["refresh_token"]}

        with capture_logs() as logs:
            logout_response, refresh_response = await run_second_behind_first(
                independent_client.post(API_AUTH_LOGOUT_URL, json=payload),
                independent_client.post(API_AUTH_REFRESH_URL, json=payload),
                gate=held_update,
                session_factory=independent_session_factory,
            )

        assert logout_response.status_code == status.HTTP_204_NO_CONTENT
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        stored_session = await self.stored_session(independent_session_factory, session_id)
        assert stored_session.revoked_reason == SessionRevocationReason.LOGOUT
        logout_matches = [log["match"] for log in logs if log["event"] == "user_logout_success"]
        revoked_session_events = [
            log for log in logs if log["event"] == "refresh_token_used_on_revoked_session"
        ]
        assert logout_matches == ["current"]
        assert len(revoked_session_events) == 1


class TestAuthLogging:
    async def test_auth_logs_exclude_email_addresses(
        self,
        client: AsyncClient,
        registered_user: UserData,
    ):
        unknown_email = "unknown-login@example.com"
        wrong_password = "wrong-password"
        login_attempts = [
            (registered_user["email"], registered_user["password"], status.HTTP_200_OK),
            (registered_user["email"], wrong_password, status.HTTP_401_UNAUTHORIZED),
            (unknown_email, wrong_password, status.HTTP_401_UNAUTHORIZED),
        ]

        with capture_logs() as logs:
            for email, password, expected_status in login_attempts:
                response = await client.post(
                    API_AUTH_LOGIN_URL,
                    json={"email": email, "password": password},
                )
                assert response.status_code == expected_status

        expected_events = [
            "user_authenticate_success",
            "user_authenticate_failed",
            "user_authenticate_failed",
        ]
        assert [
            entry["event"] for entry in logs if entry["event"].startswith("user_authenticate_")
        ] == expected_events
        sensitive_values = [registered_user["email"], unknown_email]
        serialized_logs = json.dumps(logs, default=str)
        for sensitive_value in sensitive_values:
            assert sensitive_value not in serialized_logs

    async def test_auth_logs_exclude_tokens_and_refresh_secrets(
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

            # A session of its own: a logout with a stale token revokes it, so the logout
            # above must not share it
            reuse_logout_login_response = await client.post(
                API_AUTH_LOGIN_URL,
                json={"email": registered_user["email"], "password": registered_user["password"]},
            )
            assert reuse_logout_login_response.status_code == status.HTTP_200_OK
            reuse_logout_tokens = reuse_logout_login_response.json()
            reuse_logout_session_id = uuid.UUID(
                verify_token(reuse_logout_tokens["access_token"])["sid"]
            )
            wrong_refresh_token = create_refresh_token(reuse_logout_session_id, wrong_secret)
            reuse_logout_response = await client.post(
                API_AUTH_LOGOUT_URL, json={"refresh_token": wrong_refresh_token}
            )
            assert reuse_logout_response.status_code == status.HTTP_204_NO_CONTENT

        expected_events = {
            "user_authenticate_success",
            "user_session_refresh_success",
            "refresh_token_rejected_session_not_found",
            "refresh_token_rejected_invalid_signature",
            "logout_token_reuse_detected",
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
        for tokens in (initial_tokens, rotated_tokens, compromised_tokens, reuse_logout_tokens):
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


class TestGetMeAccessToken:
    # Valid in every claim and signed with the real key, so a test that breaks exactly one
    # of them is rejected for that claim alone
    @pytest.fixture
    def valid_claims(self, authenticated_user: AuthenticatedUser) -> dict[str, str | float]:
        expires_at = utc_now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        return {
            "sub": str(authenticated_user["user"]["id"]),
            "sid": str(session_id_from_headers(authenticated_user["headers"])),
            "exp": expires_at.timestamp(),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }

    async def test_get_me_valid_claims_succeeds(
        self,
        client: AsyncClient,
        valid_claims: dict[str, str | float],
    ):
        token = encode_test_jwt(valid_claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_get_me_token_without_exp_unauthorized(
        self,
        client: AsyncClient,
        valid_claims: dict[str, str | float],
    ):
        token = encode_test_jwt(
            without_claim(valid_claims, "exp"), settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    @pytest.mark.parametrize(
        "break_claims",
        [
            pytest.param(break_claims, id=name)
            for name, break_claims in ISSUER_AUDIENCE_DEFECTS.items()
        ],
    )
    async def test_get_me_invalid_issuer_or_audience_unauthorized(
        self,
        client: AsyncClient,
        valid_claims: dict[str, str | float],
        break_claims: ClaimsBreaker,
    ):
        token = encode_test_jwt(
            break_claims(valid_claims), settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_token_without_sub_unauthorized(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        session_id = session_id_from_headers(authenticated_user["headers"])
        token = create_access_token({"sid": str(session_id)})

        response = await client.get(
            API_USERS_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert_no_field_errors(response, ErrorCode.AUTHENTICATION_REQUIRED)

    async def test_get_me_refresh_token_as_bearer_unauthorized(
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

    async def test_get_me_token_without_sid_unauthorized(
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

    async def test_get_me_invalid_sid_unauthorized(
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

    async def test_get_me_unknown_session_unauthorized(
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

    async def test_get_me_revoked_session_unauthorized(
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

    async def test_get_me_expired_session_unauthorized(
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

    async def test_get_me_other_users_session_unauthorized(
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

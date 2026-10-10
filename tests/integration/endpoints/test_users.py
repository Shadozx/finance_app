import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import utc_now
from app.core.error_codes import ErrorCode, FieldErrorCode
from app.models import SessionRevocationReason, UserSession
from app.services.user_session_service import SESSION_NOT_FOUND_MESSAGE
from tests.integration.endpoints.helpers import (
    assert_field_error,
    assert_no_field_errors,
    assert_validation_error,
    session_id_from_headers,
)
from tests.integration.endpoints.types import AuthenticatedUser

API_USERS_ME = "/api/v1/users/me"
API_USERS_ME_UPDATE_USERNAME = "/api/v1/users/me/username"
API_USERS_ME_UPDATE_PASSWORD = "/api/v1/users/me/password"
API_USERS_ME_SESSIONS = "/api/v1/users/me/sessions"
API_AUTH_LOGIN = "/api/v1/auth/login"
API_AUTH_REFRESH = "/api/v1/auth/refresh"

SECOND_DEVICE_USER_AGENT = "Second device browser"
SESSION_TIME_OFFSET = timedelta(days=1)


@pytest.fixture
async def second_device_tokens(
    client: AsyncClient, authenticated_user: AuthenticatedUser
) -> dict[str, str]:
    response = await client.post(
        API_AUTH_LOGIN,
        json={
            "email": authenticated_user["user"]["email"],
            "password": authenticated_user["user"]["password"],
        },
        headers={"User-Agent": SECOND_DEVICE_USER_AGENT},
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()


@pytest.fixture
def second_device_headers(second_device_tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {second_device_tokens['access_token']}"}


class TestGetMe:
    async def test_get_me_success(self, client: AsyncClient, authenticated_user: AuthenticatedUser):
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

    async def test_get_me_without_token(self, client: AsyncClient):
        response = await client.get(
            API_USERS_ME,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()


class TestGetSessions:
    async def test_get_sessions_marks_current_device_and_excludes_other_users(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        second_device_headers: dict[str, str],
        other_authenticated_user: AuthenticatedUser,
    ):
        current_session_id = str(session_id_from_headers(authenticated_user["headers"]))
        second_session_id = str(session_id_from_headers(second_device_headers))
        other_session_id = str(session_id_from_headers(other_authenticated_user["headers"]))
        expected_session_ids = {current_session_id, second_session_id}
        expected_fields = {"id", "user_agent", "created_at", "last_used_at", "is_current"}
        default_limit = 200
        default_offset = 0

        for headers in (authenticated_user["headers"], second_device_headers):
            response = await client.get(API_USERS_ME_SESSIONS, headers=headers)

            assert response.status_code == status.HTTP_200_OK
            body = response.json()
            assert body["limit"] == default_limit
            assert body["offset"] == default_offset
            assert body["has_more"] is False
            assert {item["id"] for item in body["items"]} == expected_session_ids
            assert other_session_id not in {item["id"] for item in body["items"]}
            requesting_session_id = str(session_id_from_headers(headers))
            for item in body["items"]:
                assert set(item) == expected_fields
                assert item["is_current"] is (item["id"] == requesting_session_id)
                assert datetime.fromisoformat(item["created_at"]).tzinfo is not None
                assert datetime.fromisoformat(item["last_used_at"]).tzinfo is not None
                if item["id"] == second_session_id:
                    assert item["user_agent"] == SECOND_DEVICE_USER_AGENT

    async def test_get_sessions_paginates_without_duplicates(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        second_device_headers: dict[str, str],
    ):
        page_size = 1
        expected_session_ids = [
            str(session_id_from_headers(second_device_headers)),
            str(session_id_from_headers(authenticated_user["headers"])),
        ]
        for offset, expected_session_id in enumerate(expected_session_ids):
            response = await client.get(
                API_USERS_ME_SESSIONS,
                params={"limit": page_size, "offset": offset},
                headers=authenticated_user["headers"],
            )

            assert response.status_code == status.HTTP_200_OK
            body = response.json()
            assert [item["id"] for item in body["items"]] == [expected_session_id]
            assert body["limit"] == page_size
            assert body["offset"] == offset
            assert body["has_more"] is (offset + page_size < len(expected_session_ids))

        response = await client.get(
            API_USERS_ME_SESSIONS,
            params={"limit": page_size, "offset": len(expected_session_ids)},
            headers=authenticated_user["headers"],
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == []
        assert response.json()["has_more"] is False

    async def test_get_sessions_excludes_expired_sessions(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
        second_device_headers: dict[str, str],
    ):
        expired_session_id = session_id_from_headers(second_device_headers)
        await test_session.execute(
            update(UserSession)
            .where(UserSession.id == expired_session_id)
            .values(expires_at=utc_now() - SESSION_TIME_OFFSET)
        )

        response = await client.get(API_USERS_ME_SESSIONS, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_200_OK
        expected_session_ids = [str(session_id_from_headers(authenticated_user["headers"]))]
        assert [item["id"] for item in response.json()["items"]] == expected_session_ids

    @pytest.mark.parametrize(
        "field, value, code",
        [
            ("limit", 0, FieldErrorCode.GREATER_THAN_EQUAL),
            ("limit", 501, FieldErrorCode.LESS_THAN_EQUAL),
            ("offset", -1, FieldErrorCode.GREATER_THAN_EQUAL),
        ],
    )
    async def test_get_sessions_validates_pagination(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        field: str,
        value: int,
        code: FieldErrorCode,
    ):
        response = await client.get(
            API_USERS_ME_SESSIONS,
            params={field: value},
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["query", field], code)

    async def test_get_sessions_without_token(self, client: AsyncClient):
        response = await client.get(API_USERS_ME_SESSIONS)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRevokeSession:
    async def test_revoke_session_rejects_other_device_tokens_and_hides_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
        second_device_tokens: dict[str, str],
        second_device_headers: dict[str, str],
    ):
        second_session_id = session_id_from_headers(second_device_headers)

        response = await client.delete(
            f"{API_USERS_ME_SESSIONS}/{second_session_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == second_session_id)
        )
        assert revoked_reason == SessionRevocationReason.REVOKED_BY_USER
        other_response = await client.get(API_USERS_ME, headers=second_device_headers)
        assert other_response.status_code == status.HTTP_401_UNAUTHORIZED
        refresh_response = await client.post(
            API_AUTH_REFRESH, json={"refresh_token": second_device_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        current_response = await client.get(API_USERS_ME, headers=authenticated_user["headers"])
        assert current_response.status_code == status.HTTP_200_OK
        sessions_response = await client.get(
            API_USERS_ME_SESSIONS, headers=authenticated_user["headers"]
        )
        assert sessions_response.status_code == status.HTTP_200_OK
        expected_session_ids = [str(session_id_from_headers(authenticated_user["headers"]))]
        assert [item["id"] for item in sessions_response.json()["items"]] == expected_session_ids

    async def test_revoke_session_rejects_foreign_session_and_keeps_it_active(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        other_authenticated_user: AuthenticatedUser,
    ):
        foreign_session_id = session_id_from_headers(other_authenticated_user["headers"])

        response = await client.delete(
            f"{API_USERS_ME_SESSIONS}/{foreign_session_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["detail"] == SESSION_NOT_FOUND_MESSAGE
        assert_no_field_errors(response, ErrorCode.NOT_FOUND)
        other_response = await client.get(API_USERS_ME, headers=other_authenticated_user["headers"])
        assert other_response.status_code == status.HTTP_200_OK

    @pytest.mark.parametrize("session_state", ["missing", "revoked", "expired"])
    async def test_revoke_session_rejects_unavailable_session(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
        second_device_headers: dict[str, str],
        session_state: str,
    ):
        session_id = session_id_from_headers(second_device_headers)
        now = utc_now()
        if session_state == "missing":
            session_id = uuid.uuid4()
        elif session_state == "revoked":
            await test_session.execute(
                update(UserSession)
                .where(UserSession.id == session_id)
                .values(revoked_at=now, revoked_reason=SessionRevocationReason.REUSE_DETECTED)
            )
        else:
            await test_session.execute(
                update(UserSession)
                .where(UserSession.id == session_id)
                .values(expires_at=now - SESSION_TIME_OFFSET)
            )
        state_query = select(UserSession.revoked_at, UserSession.revoked_reason).where(
            UserSession.id == session_id
        )
        original_state = (await test_session.execute(state_query)).one_or_none()

        response = await client.delete(
            f"{API_USERS_ME_SESSIONS}/{session_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["detail"] == SESSION_NOT_FOUND_MESSAGE
        assert_no_field_errors(response, ErrorCode.NOT_FOUND)
        assert (await test_session.execute(state_query)).one_or_none() == original_state

    async def test_revoke_session_rejects_malformed_uuid(
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
    ):
        invalid_session_id = "not-a-uuid"
        response = await client.delete(
            f"{API_USERS_ME_SESSIONS}/{invalid_session_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == ErrorCode.VALIDATION_FAILED
        assert response.json()["errors"][0]["loc"] == ["path", "session_id"]

    async def test_revoke_session_can_revoke_current_session(
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
    ):
        session_id = session_id_from_headers(authenticated_user["headers"])
        response = await client.delete(
            f"{API_USERS_ME_SESSIONS}/{session_id}", headers=authenticated_user["headers"]
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        me_response = await client.get(API_USERS_ME, headers=authenticated_user["headers"])
        assert me_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_revoke_session_without_token(self, client: AsyncClient):
        session_id = uuid.uuid4()
        response = await client.delete(f"{API_USERS_ME_SESSIONS}/{session_id}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRevokeOtherSessions:
    async def test_revoke_other_sessions_keeps_current_and_foreign_sessions(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
        second_device_tokens: dict[str, str],
        second_device_headers: dict[str, str],
        other_authenticated_user: AuthenticatedUser,
    ):
        response = await client.delete(API_USERS_ME_SESSIONS, headers=authenticated_user["headers"])

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""
        current_response = await client.get(API_USERS_ME, headers=authenticated_user["headers"])
        assert current_response.status_code == status.HTTP_200_OK
        second_response = await client.get(API_USERS_ME, headers=second_device_headers)
        assert second_response.status_code == status.HTTP_401_UNAUTHORIZED
        refresh_response = await client.post(
            API_AUTH_REFRESH, json={"refresh_token": second_device_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
        foreign_response = await client.get(
            API_USERS_ME, headers=other_authenticated_user["headers"]
        )
        assert foreign_response.status_code == status.HTTP_200_OK
        sessions_response = await client.get(
            API_USERS_ME_SESSIONS, headers=authenticated_user["headers"]
        )
        assert sessions_response.status_code == status.HTTP_200_OK
        expected_session_ids = [str(session_id_from_headers(authenticated_user["headers"]))]
        assert [item["id"] for item in sessions_response.json()["items"]] == expected_session_ids

        repeated_response = await client.delete(
            API_USERS_ME_SESSIONS, headers=authenticated_user["headers"]
        )
        assert repeated_response.status_code == status.HTTP_204_NO_CONTENT
        assert repeated_response.content == b""

    async def test_revoke_other_sessions_without_token(self, client: AsyncClient):
        response = await client.delete(API_USERS_ME_SESSIONS)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateUsername:
    async def test_update_username_success(
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
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
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
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
            },
        )

        assert register_response.status_code == status.HTTP_201_CREATED

        response = await client.put(
            API_USERS_ME_UPDATE_USERNAME,
            json=payload,
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        assert_field_error(response, ErrorCode.ALREADY_EXISTS, ["body", "new_username"])

    @pytest.mark.parametrize(
        "payload, reason",
        [
            ({"new_username": "ab"}, "too_short"),
            ({"new_username": "a" * 55}, "too_long"),
            ({"new_username": "user name"}, "contains_space"),
            ({"new_username": "user@name"}, "special_chars"),
            ({}, "missing_new_username"),
        ],
    )
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
            API_USERS_ME_UPDATE_USERNAME, json={"new_username": "newusername"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

    async def test_update_username_same_as_current(
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
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
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
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

        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": authenticated_user["user"]["email"],
                "password": payload["new_password"],
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        assert "access_token" in login_response.json()

        old_login = await client.post(
            "/api/v1/auth/login",
            json={
                "email": authenticated_user["user"]["email"],
                "password": authenticated_user["user"]["password"],
            },
        )

        assert old_login.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_password_keeps_current_session_and_revokes_other_sessions(
        self,
        client: AsyncClient,
        test_session: AsyncSession,
        authenticated_user: AuthenticatedUser,
        second_device_tokens: dict[str, str],
        second_device_headers: dict[str, str],
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

        me_response = await client.get(
            API_USERS_ME,
            headers=authenticated_user["headers"],
        )

        assert me_response.status_code == status.HTTP_200_OK

        other_response = await client.get(API_USERS_ME, headers=second_device_headers)
        assert other_response.status_code == status.HTTP_401_UNAUTHORIZED

        refresh_response = await client.post(
            API_AUTH_REFRESH, json={"refresh_token": second_device_tokens["refresh_token"]}
        )
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

        other_session_id = session_id_from_headers(second_device_headers)
        revoked_reason = await test_session.scalar(
            select(UserSession.revoked_reason).where(UserSession.id == other_session_id)
        )
        assert revoked_reason == SessionRevocationReason.PASSWORD_CHANGED

        sessions_response = await client.get(
            API_USERS_ME_SESSIONS, headers=authenticated_user["headers"]
        )
        assert sessions_response.status_code == status.HTTP_200_OK
        expected_session_ids = [str(session_id_from_headers(authenticated_user["headers"]))]
        assert [item["id"] for item in sessions_response.json()["items"]] == expected_session_ids

    async def test_update_password_wrong_current_password(
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
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

        assert_field_error(response, ErrorCode.INVALID_CREDENTIALS, ["body", "current_password"])

    async def test_update_password_same_as_current(
        self, client: AsyncClient, authenticated_user: AuthenticatedUser
    ):
        response = await client.put(
            API_USERS_ME_UPDATE_PASSWORD,
            json={
                "current_password": authenticated_user["user"]["password"],
                "new_password": authenticated_user["user"]["password"],
            },
            headers=authenticated_user["headers"],
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert_validation_error(response, ["body", "new_password"], FieldErrorCode.SAME_AS_CURRENT)

    @pytest.mark.parametrize(
        "payload, reason",
        [
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
        ],
    )
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
            json={"current_password": "Password123", "new_password": "NewUsername123"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        assert "detail" in response.json()

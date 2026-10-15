import json
from collections.abc import AsyncIterator

import structlog
from fastapi import status
from httpx import AsyncClient, Response
from pytest_mock import MockerFixture
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from app.api.v1.endpoints.auth import LOGIN_REQUESTS_PER_MINUTE
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.middleware import MAX_REQUEST_BODY_BYTES
from app.main import app
from app.repositories import CategoryRepository
from tests.integration.endpoints.helpers import (
    assert_field_error,
    category_payload,
    create_category,
    register_payload,
)
from tests.integration.endpoints.types import AuthenticatedUser, UserData

API_CATEGORIES = "/api/v1/categories"
API_REGISTER = "/api/v1/auth/register"
API_LOGIN = "/api/v1/auth/login"
API_HEALTH = "/api/v1/health"
API_HEALTH_READY = "/api/v1/health/ready"
API_NONEXISTENT = "/api/v1/nonexistent"


def assert_error_response(
    response: Response,
    expected_status: int,
    expected_code: ErrorCode,
    *,
    expected_keys: tuple[str, ...] = ("status", "code", "detail"),
) -> None:
    body = response.json()

    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/problem+json"
    assert set(body) == set(expected_keys)
    assert body["status"] == response.status_code
    assert body["code"] == expected_code
    assert isinstance(body["detail"], str)


class TestErrorHandling:
    async def test_router_not_found_response_format(self, client: AsyncClient):
        response = await client.get(API_NONEXISTENT)

        assert_error_response(response, status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND)

    async def test_method_not_allowed_response_format(self, client: AsyncClient):
        response = await client.post(API_HEALTH)

        assert_error_response(
            response, status.HTTP_405_METHOD_NOT_ALLOWED, ErrorCode.METHOD_NOT_ALLOWED
        )
        assert "GET" in response.headers["Allow"]

    async def test_missing_token_response_format(self, client: AsyncClient):
        response = await client.get(API_CATEGORIES)

        assert_error_response(
            response, status.HTTP_401_UNAUTHORIZED, ErrorCode.AUTHENTICATION_REQUIRED
        )

    async def test_duplicate_category_response_format(
        self,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        payload = category_payload(name="Duplicate category")
        headers = authenticated_user["headers"]
        await create_category(client, payload, headers)

        response = await client.post(API_CATEGORIES, json=payload, headers=headers)

        assert_error_response(
            response,
            status.HTTP_409_CONFLICT,
            ErrorCode.ALREADY_EXISTS,
            expected_keys=("status", "code", "detail", "errors"),
        )
        assert_field_error(response, ErrorCode.ALREADY_EXISTS, ["body", "name"])

    async def test_request_validation_response_format(self, client: AsyncClient):
        short_password = "Z9#v2!"

        response = await client.post(API_REGISTER, json=register_payload(password=short_password))

        assert_error_response(
            response,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.VALIDATION_FAILED,
            expected_keys=("status", "code", "detail", "errors"),
        )
        body = response.json()
        assert short_password not in response.text
        assert body["detail"] == "Request validation failed"
        assert body["errors"][0]["loc"] == ["body", "password"]
        assert all(set(error) == {"loc", "code", "detail"} for error in body["errors"])

    async def test_login_rate_limit_response_format(
        self,
        mocker: MockerFixture,
        client: AsyncClient,
        registered_user: UserData,
    ):
        incorrect_password = "IncorrectPassword123"
        payload = {"email": registered_user["email"], "password": incorrect_password}
        limiter = app.state.limiter
        limiter.reset()
        mocker.patch.object(limiter, "enabled", True)

        try:
            for _ in range(LOGIN_REQUESTS_PER_MINUTE):
                response = await client.post(API_LOGIN, json=payload)
                assert_error_response(
                    response, status.HTTP_401_UNAUTHORIZED, ErrorCode.INVALID_CREDENTIALS
                )

            with capture_logs() as logs:
                response = await client.post(API_LOGIN, json=payload)

            assert_error_response(
                response, status.HTTP_429_TOO_MANY_REQUESTS, ErrorCode.RATE_LIMITED
            )
            assert all(log["event"] != "unmapped_http_exception" for log in logs)
        finally:
            limiter.reset()

    async def test_repository_failure_response_format(
        self,
        mocker: MockerFixture,
        client: AsyncClient,
        authenticated_user: AuthenticatedUser,
    ):
        mocker.patch.object(settings, "DEBUG", False)
        mocker.patch.object(
            CategoryRepository,
            "get_by_user_and_name",
            side_effect=RuntimeError("Repository unavailable"),
        )
        payload = category_payload()

        # capture_logs drops the configured processors, so request_id must be merged back in
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            response = await client.post(
                API_CATEGORIES, json=payload, headers=authenticated_user["headers"]
            )

        assert_error_response(
            response, status.HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_ERROR
        )
        assert response.json()["detail"] == "Internal server error"

        # X-Request-ID is set inside CORSMiddleware: its presence means the 500 went through it
        unhandled_logs = [log for log in logs if log["event"] == "unhandled_exception"]
        assert len(unhandled_logs) == 1
        assert unhandled_logs[0]["request_id"] == response.headers["X-Request-ID"]

    async def test_readiness_failure_response_format(
        self,
        mocker: MockerFixture,
        client: AsyncClient,
        test_session: AsyncSession,
    ):
        mocker.patch.object(
            test_session, "execute", side_effect=RuntimeError("Database unavailable")
        )

        response = await client.get(API_HEALTH_READY)

        assert_error_response(response, status.HTTP_503_SERVICE_UNAVAILABLE, ErrorCode.UNAVAILABLE)


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
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json() == {
            "status": response.status_code,
            "code": ErrorCode.ALREADY_EXISTS,
            "detail": "Resource with these values already exists",
        }


class TestRequestBodyLimit:
    async def test_oversized_body_response_format(self, client: AsyncClient):
        """Content-Length alone is enough to reject: the body is never read."""
        response = await client.post(
            API_LOGIN,
            content=b"a" * (MAX_REQUEST_BODY_BYTES + 1),
            headers={"Content-Type": "application/json"},
        )

        assert_error_response(
            response, status.HTTP_413_CONTENT_TOO_LARGE, ErrorCode.CONTENT_TOO_LARGE
        )
        assert "X-Request-ID" in response.headers

    async def test_oversized_chunked_body_response_format(self, client: AsyncClient):
        """Without Content-Length the bytes are counted as they arrive."""
        chunk = b"a" * (MAX_REQUEST_BODY_BYTES // 2 + 1)

        async def chunked_body() -> AsyncIterator[bytes]:
            yield chunk
            yield chunk

        response = await client.post(
            API_LOGIN,
            content=chunked_body(),
            headers={"Content-Type": "application/json"},
        )

        assert "Content-Length" not in response.request.headers
        assert_error_response(
            response, status.HTTP_413_CONTENT_TOO_LARGE, ErrorCode.CONTENT_TOO_LARGE
        )
        assert "X-Request-ID" in response.headers

    async def test_body_at_limit_accepted(self, client: AsyncClient):
        """The schema ignores the padding field, so the request reaches the login check."""
        credentials = {"email": "unknownemail@test.com", "password": "Password123"}
        padding_size = MAX_REQUEST_BODY_BYTES - len(json.dumps({**credentials, "padding": ""}))
        body = json.dumps({**credentials, "padding": "a" * padding_size}).encode()

        assert len(body) == MAX_REQUEST_BODY_BYTES

        response = await client.post(
            API_LOGIN,
            content=body,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

import json
from datetime import datetime
from typing import Annotated

import pytest
from fastapi import FastAPI, Request, status
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field, ValidationError
from pytest_mock import MockerFixture
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException
from structlog.testing import capture_logs

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exception_handlers import (
    app_exception_handler,
    global_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    request_validation_handler,
)
from app.core.exceptions import NotFoundException
from app.main import app


@pytest.fixture
def http_request():
    return Request({"type": "http", "path": "/test", "headers": []})


async def test_app_exception_handler_inherits_status_and_code(http_request: Request):
    class MissingAccountException(NotFoundException):
        pass

    detail = "Account not found"
    response = await app_exception_handler(http_request, MissingAccountException(detail))

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert json.loads(response.body) == {
        "status": response.status_code,
        "code": ErrorCode.NOT_FOUND,
        "detail": detail,
    }


async def test_request_validation_handler_preserves_locations_and_omits_inputs(
    http_request: Request,
):
    class SplitAmounts(BaseModel):
        splits: list[Annotated[int, Field(gt=0)]]

    private_amount = "private-amount"
    invalid_amount = 0
    with pytest.raises(ValidationError) as validation_error:
        SplitAmounts(splits=[private_amount, invalid_amount])

    exception = RequestValidationError(validation_error.value.errors())
    response = await request_validation_handler(http_request, exception)
    body = json.loads(response.body)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"] == "application/problem+json"
    assert set(body) == {"status", "code", "detail", "errors"}
    assert body["status"] == response.status_code
    assert body["code"] == ErrorCode.VALIDATION_FAILED
    assert body["detail"] == "Request validation failed"
    assert body["errors"][0]["loc"] == ["splits", 0]
    assert body["errors"][0]["code"] == "int_parsing"
    assert body["errors"][1]["loc"] == ["splits", 1]
    assert body["errors"][1]["code"] == "greater_than"
    assert all(set(error) == {"loc", "code", "detail"} for error in body["errors"])
    assert private_amount not in response.body.decode()


async def test_pydantic_validation_error_returns_internal_error(mocker: MockerFixture):
    class ResponseData(BaseModel):
        created_at: datetime

    mocker.patch.object(settings, "DEBUG", False)
    invalid_response = {"created_at": None}
    invalid_response_path = "/invalid-response"
    test_app = FastAPI(exception_handlers=app.exception_handlers)

    async def invalid_response_endpoint():
        return ResponseData.model_validate(invalid_response)

    test_app.add_api_route(invalid_response_path, invalid_response_endpoint, methods=["GET"])
    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    with capture_logs() as logs:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(invalid_response_path)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "status": response.status_code,
        "code": ErrorCode.INTERNAL_ERROR,
        "detail": "Internal server error",
    }
    assert any(log["event"] == "unhandled_exception" and log["exc_info"] is True for log in logs)


@pytest.mark.parametrize("debug", [False, True])
async def test_global_exception_handler_debug_detail(
    http_request: Request, mocker: MockerFixture, debug: bool
):
    mocker.patch.object(settings, "DEBUG", debug)
    private_detail = "Private database failure"
    exception = RuntimeError(private_detail)

    response = await global_exception_handler(http_request, exception)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert json.loads(response.body) == {
        "status": response.status_code,
        "code": ErrorCode.INTERNAL_ERROR,
        "detail": f"RuntimeError: {private_detail}" if debug else "Internal server error",
    }


async def test_integrity_error_handler_non_unique_violation_is_internal_error(
    http_request: Request, mocker: MockerFixture
):
    class ForeignKeyViolation(Exception):
        sqlstate = "23503"

    mocker.patch.object(settings, "DEBUG", False)
    exception = IntegrityError(None, None, ForeignKeyViolation("Missing foreign key"))

    response = await integrity_error_handler(http_request, exception)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert json.loads(response.body) == {
        "status": response.status_code,
        "code": ErrorCode.INTERNAL_ERROR,
        "detail": "Internal server error",
    }


async def test_http_exception_handler_unmapped_status_logs_warning(http_request: Request):
    unmapped_status = status.HTTP_418_IM_A_TEAPOT
    detail = "Unmapped HTTP error"

    with capture_logs() as logs:
        response = await http_exception_handler(
            http_request, HTTPException(status_code=unmapped_status, detail=detail)
        )

    assert response.status_code == unmapped_status
    assert json.loads(response.body) == {
        "status": unmapped_status,
        "code": ErrorCode.INTERNAL_ERROR,
        "detail": detail,
    }
    assert logs == [
        {
            "event": "unmapped_http_exception",
            "log_level": "warning",
            "status_code": unmapped_status,
            "path": http_request.url.path,
        }
    ]


async def test_http_exception_handler_converts_non_string_detail(http_request: Request):
    detail = {"reason": "Database unavailable"}
    exception = FastAPIHTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)

    response = await http_exception_handler(http_request, exception)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers["content-type"] == "application/problem+json"
    assert json.loads(response.body) == {
        "status": response.status_code,
        "code": ErrorCode.UNAVAILABLE,
        "detail": str(detail),
    }


def test_openapi_uses_error_response_for_validation():
    schema = app.openapi()

    for path_item in schema["paths"].values():
        for operation in path_item.values():
            responses = operation["responses"]
            if not (operation.get("parameters") or operation.get("requestBody")):
                assert "422" not in responses
                continue
            response = responses["422"]
            assert set(response["content"]) == {"application/problem+json"}
            assert response["content"]["application/problem+json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
    registration = schema["paths"]["/api/v1/auth/register"]["post"]["responses"]
    assert set(registration["201"]["content"]) == {"application/json"}
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert "ErrorItem" in schema["components"]["schemas"]
    assert "ErrorCode" in schema["components"]["schemas"]
    assert "HTTPValidationError" not in schema["components"]["schemas"]


@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/health/ready"])
def test_openapi_health_has_no_validation_response(path: str):
    schema = app.openapi()

    assert "422" not in schema["paths"][path]["get"]["responses"]

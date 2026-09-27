from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.schemas.error import ErrorItem, ErrorResponse

logger = structlog.get_logger()

UNIQUE_VIOLATION = "23505"
HTTP_ERROR_CODES = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.UNAVAILABLE,
}


def build_error_response(
    status_code: int,
    code: ErrorCode,
    detail: str,
    *,
    errors: list[ErrorItem] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response = ErrorResponse(status=status_code, code=code, detail=detail, errors=errors)
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json", exclude_none=True),
        headers=headers,
        media_type="application/problem+json",
    )


def validation_error_items(errors: Sequence[Mapping[str, Any]]) -> list[ErrorItem]:
    return [
        ErrorItem(loc=list(error["loc"]), code=error["type"], detail=error["msg"])
        for error in errors
    ]


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    sqlstate = getattr(exc.orig, "sqlstate", None)

    if sqlstate != UNIQUE_VIOLATION:
        return await global_exception_handler(request, exc)

    logger.warning("db_unique_violation", path=request.url.path)

    return build_error_response(
        409,
        ErrorCode.ALREADY_EXISTS,
        "Resource with these values already exists",
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return build_error_response(exc.status_code, exc.code, exc.message)


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return build_error_response(
        422,
        ErrorCode.VALIDATION_FAILED,
        "Request validation failed",
        errors=validation_error_items(exc.errors()),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = HTTP_ERROR_CODES.get(exc.status_code)
    if code is None:
        logger.warning(
            "unmapped_http_exception", status_code=exc.status_code, path=request.url.path
        )
        code = ErrorCode.INTERNAL_ERROR

    return build_error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=True)

    detail = f"{type(exc).__name__}: {exc}" if settings.DEBUG else "Internal server error"
    return build_error_response(500, ErrorCode.INTERNAL_ERROR, detail)

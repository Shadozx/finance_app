from fastapi import Request
from fastapi.responses import JSONResponse

from sqlalchemy.exc import IntegrityError

from pydantic import ValidationError

import structlog

from app.core.config import settings
from app.core.exceptions import AppException

logger = structlog.get_logger()

UNIQUE_VIOLATION = "23505"


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    sqlstate = getattr(exc.orig, "sqlstate", None)

    if sqlstate != UNIQUE_VIOLATION:
        return await global_exception_handler(request, exc)

    logger.warning("db_unique_violation", path=request.url.path)

    return JSONResponse(
        status_code=409,
        content={"detail": "Resource with these values already exists"},
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    status_map = {
        "NotFoundException": 404,
        "ValueExistsException": 409,
        "NotAllowedActionException": 409,
        "AuthenticationException": 401,
        "PermissionException": 403,
        "ValidationException": 400
    }
    status_code = status_map.get(type(exc).__name__, 500)

    return JSONResponse(status_code=status_code, content={"detail": exc.message})


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    errors = [error["msg"] for error in exc.errors()]

    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=True)

    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "type": type(exc).__name__},
        )

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

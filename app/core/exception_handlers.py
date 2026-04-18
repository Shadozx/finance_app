from fastapi import Request
from fastapi.responses import JSONResponse

from pydantic import ValidationError

import structlog

from app.core.exceptions import AppException

logger = structlog.get_logger()


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

    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

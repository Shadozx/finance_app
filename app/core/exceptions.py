from dataclasses import dataclass
from typing import ClassVar

from app.core.error_codes import ErrorCode

REQUEST_VALIDATION_FAILED_MESSAGE = "Request validation failed"


@dataclass(frozen=True)
class FieldError:
    loc: tuple[str | int, ...]
    code: str
    detail: str


class AppException(Exception):
    status_code: ClassVar[int] = 500
    default_code: ClassVar[ErrorCode | None] = ErrorCode.INTERNAL_ERROR
    default_message: ClassVar[str] = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | None = None,
        loc: tuple[str | int, ...] | None = None,
        errors: list[FieldError] | None = None,
    ):
        if loc is not None and errors is not None:
            raise TypeError("loc and errors cannot be provided together")

        resolved_code = code if code is not None else self.default_code
        if resolved_code is None:
            raise TypeError("An error code is required")

        self.message = self.default_message if message is None else message
        self.code = resolved_code
        self.errors = (
            [FieldError(loc=loc, code=resolved_code, detail=self.message)]
            if loc is not None
            else list(errors or [])
        )
        super().__init__(self.message)


class NotFoundException(AppException):
    status_code = 404
    default_code = ErrorCode.NOT_FOUND
    default_message = "Resource not found"


class ValueExistsException(AppException):
    status_code = 409
    default_code = ErrorCode.ALREADY_EXISTS
    default_message = "Value already exists"


class NotAllowedActionException(AppException):
    status_code = 409
    default_code = None
    default_message = "Action not allowed"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode,
        loc: tuple[str | int, ...] | None = None,
        errors: list[FieldError] | None = None,
    ):
        super().__init__(message, code=code, loc=loc, errors=errors)


class AuthenticationException(AppException):
    status_code = 401
    default_code = ErrorCode.AUTHENTICATION_REQUIRED
    default_message = "Authentication failed"


class ValidationException(AppException):
    status_code = 422
    default_code = ErrorCode.VALIDATION_FAILED
    default_message = REQUEST_VALIDATION_FAILED_MESSAGE

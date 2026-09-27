from typing import ClassVar

from app.core.error_codes import ErrorCode


class AppException(Exception):
    status_code: ClassVar[int] = 500
    default_code: ClassVar[ErrorCode | None] = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str, *, code: ErrorCode | None = None):
        resolved_code = code if code is not None else self.default_code
        if resolved_code is None:
            raise TypeError("An error code is required")

        self.message = message
        self.code = resolved_code
        super().__init__(message)


class NotFoundException(AppException):
    status_code = 404
    default_code = ErrorCode.NOT_FOUND

    def __init__(self, message: str = "Resource not found", *, code: ErrorCode | None = None):
        super().__init__(message, code=code)


class ValueExistsException(AppException):
    status_code = 409
    default_code = ErrorCode.ALREADY_EXISTS

    def __init__(self, message: str = "Value already exists", *, code: ErrorCode | None = None):
        super().__init__(message, code=code)


class NotAllowedActionException(AppException):
    status_code = 409
    default_code = None

    def __init__(self, message: str = "Action not allowed", *, code: ErrorCode):
        super().__init__(message, code=code)


class AuthenticationException(AppException):
    status_code = 401
    default_code = ErrorCode.AUTHENTICATION_REQUIRED

    def __init__(self, message: str = "Authentication failed", *, code: ErrorCode | None = None):
        super().__init__(message, code=code)


class ValidationException(AppException):
    status_code = 422
    default_code = ErrorCode.VALIDATION_FAILED

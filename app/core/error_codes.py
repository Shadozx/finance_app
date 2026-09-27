from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    ARCHIVED = "archived"
    TYPE_MISMATCH = "type_mismatch"
    INACTIVE = "inactive"
    ALREADY_IN_STATE = "already_in_state"
    PARTIAL_UPDATE_NOT_ALLOWED = "partial_update_not_allowed"
    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    VALIDATION_FAILED = "validation_failed"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    INTERNAL_ERROR = "internal_error"


class FieldErrorCode(StrEnum):
    MUST_MATCH = "must_match"
    NOT_ALLOWED = "not_allowed"
    MISSING = "missing"

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
    STRING_TOO_SHORT = "string_too_short"
    STRING_TOO_LONG = "string_too_long"
    STRING_PATTERN_MISMATCH = "string_pattern_mismatch"
    FINITE_NUMBER = "finite_number"
    GREATER_THAN_EQUAL = "greater_than_equal"
    GREATER_THAN = "greater_than"
    LESS_THAN_EQUAL = "less_than_equal"
    DECIMAL_MAX_PLACES = "decimal_max_places"
    PASSWORD_TOO_WEAK = "password_too_weak"
    INVALID_FORMAT = "invalid_format"
    END_BEFORE_START = "end_before_start"
    RANGE_TOO_LONG = "range_too_long"
    INCOMPLETE_RANGE = "incomplete_range"
    MUST_DIFFER = "must_differ"
    SAME_AS_CURRENT = "same_as_current"

import enum


class TransactionType(str, enum.Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class TransactionKind(str, enum.Enum):
    REGULAR = "REGULAR"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER = "TRANSFER"


class CategoryType(str, enum.Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    ANY = "ANY"


class SessionRevocationReason(str, enum.Enum):
    LOGOUT = "LOGOUT"
    REUSE_DETECTED = "REUSE_DETECTED"
    REVOKED_BY_USER = "REVOKED_BY_USER"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"


USABLE_CATEGORY_TYPES: dict[TransactionType, tuple[CategoryType, ...]] = {
    TransactionType.EXPENSE: (CategoryType.EXPENSE, CategoryType.ANY),
    TransactionType.INCOME: (CategoryType.INCOME, CategoryType.ANY),
}
"""Category types a record of the given direction may use: its own plus ANY."""

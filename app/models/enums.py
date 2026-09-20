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


USABLE_CATEGORY_TYPES: dict[TransactionType, tuple[CategoryType, ...]] = {
    TransactionType.EXPENSE: (CategoryType.EXPENSE, CategoryType.ANY),
    TransactionType.INCOME: (CategoryType.INCOME, CategoryType.ANY),
}
"""Category types a record of the given direction may use: its own plus ANY."""

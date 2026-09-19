"""Default categories created for every newly registered user."""

from app.models import CategoryType

DEFAULT_CATEGORIES: tuple[tuple[str, CategoryType], ...] = (
    ("Food", CategoryType.EXPENSE),
    ("Transport", CategoryType.EXPENSE),
    ("Housing", CategoryType.EXPENSE),
    ("Health", CategoryType.EXPENSE),
    ("Entertainment", CategoryType.EXPENSE),
    ("Salary", CategoryType.INCOME),
    ("Gifts", CategoryType.ANY),
    ("Other", CategoryType.ANY),
)

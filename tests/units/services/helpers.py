from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TypeVar

from app.models import (
    Account,
    Budget,
    Category,
    Transaction,
    TransactionTemplate,
    TransactionTemplateSplit,
    TransactionType,
    User,
)

T = TypeVar("T")


def assert_model_fields(obj, **expected_fields):
    """
    Assert that object fields match expected values.

    Args:
        obj: Model instance to check
        **expected_fields: field_name=expected_value pairs

    Example:
        assert_model_fields(user, id=1, email="test@test.com")
    """
    for field, expected_value in expected_fields.items():
        actual_value = getattr(obj, field)
        assert actual_value == expected_value, (
            f"Field '{field}' mismatch: expected {expected_value!r}, got {actual_value!r}"
        )


def as_persisted(obj: T, obj_id: int = 1) -> T:
    """Model as it comes back from add(): id assigned, column defaults applied.

    Mirrors flush(): SQLAlchemy assigns the primary key and evaluates
    Python-side `default=` callables.
    """
    obj.id = obj_id

    if hasattr(obj, "created_at") and obj.created_at is None:
        obj.created_at = datetime.now(UTC)

    return obj


def as_persisted_all(objects: list[T], start_id: int = 1) -> list[T]:
    """Models as they come back from add_all(): each gets its own id.

    Ids are sequential, mirroring how the database assigns them.
    """
    return [as_persisted(obj, start_id + index) for index, obj in enumerate(objects)]


def make_transaction(**kwargs) -> Transaction:
    """Transaction with settled fields defaulted to the operation amount.

    Cross-currency cases pass settled_amount explicitly.
    """
    kwargs.setdefault("settled_amount", kwargs["amount"])
    kwargs.setdefault("settled_currency_code", kwargs["currency_code"])
    return Transaction(**kwargs)


def make_account(**kwargs) -> Account:
    """Account with all required fields defaulted: tests pass only what they assert on."""
    kwargs.setdefault("id", 1)
    kwargs.setdefault("name", "Cash")
    kwargs.setdefault("currency_code", "UAH")
    kwargs.setdefault("user_id", 1)
    kwargs.setdefault("created_at", datetime.now(UTC))
    kwargs.setdefault("archived_at", None)
    return Account(**kwargs)


def make_category(**kwargs) -> Category:
    """Category with all required fields defaulted: tests pass only what they assert on."""
    kwargs.setdefault("id", 1)
    kwargs.setdefault("name", "Foods")
    kwargs.setdefault("user_id", 1)
    kwargs.setdefault("created_at", datetime.now(UTC))
    kwargs.setdefault("archived_at", None)

    return Category(**kwargs)


def make_budget(**kwargs) -> Budget:
    """Budget with all required fields defaulted: tests pass only what they assert on."""

    kwargs.setdefault("id", 1)
    kwargs.setdefault("name", "Food budget")
    kwargs.setdefault("amount", Decimal("5000.00"))
    kwargs.setdefault("currency_code", "UAH")
    kwargs.setdefault("category_id", 1)
    kwargs.setdefault("start_date", date(2026, 7, 1))
    kwargs.setdefault("end_date", date(2026, 7, 31))
    kwargs.setdefault("user_id", 1)

    return Budget(**kwargs)


def make_transaction_template(**kwargs) -> TransactionTemplate:
    """Transaction template with all required fields defaulted: tests pass only what they assert on."""
    kwargs.setdefault("id", 1)
    kwargs.setdefault("name", "Foods")
    kwargs.setdefault("amount", Decimal("5000.00"))
    kwargs.setdefault("currency_code", "UAH")
    kwargs.setdefault("user_id", 1)
    kwargs.setdefault("type", TransactionType.EXPENSE)
    kwargs.setdefault("created_at", datetime.now(UTC))

    return TransactionTemplate(**kwargs)


def make_transaction_template_split(**kwargs) -> TransactionTemplateSplit:
    """Template split with all required fields defaulted: tests pass only what they assert on."""
    kwargs.setdefault("id", 1)
    kwargs.setdefault("transaction_template_id", 1)
    kwargs.setdefault("category_id", 1)
    kwargs.setdefault("amount", Decimal("100.00"))
    kwargs.setdefault("description", None)

    return TransactionTemplateSplit(**kwargs)


def make_user(**kwargs) -> User:
    """User with all required fields defaulted: tests pass only what they assert on."""

    kwargs.setdefault("id", 1)
    kwargs.setdefault("username", "user")
    kwargs.setdefault("email", "user@test.com")
    kwargs.setdefault("hashed_password", "hashed_password")
    kwargs.setdefault("created_at", datetime(2026, 2, 10))

    return User(**kwargs)

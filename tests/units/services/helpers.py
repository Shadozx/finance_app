from app.models import Transaction

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
            f"Field '{field}' mismatch: expected {expected_value!r}, "
            f"got {actual_value!r}"
        )

def make_created(transaction: Transaction, transaction_id: int = 1) -> Transaction:
    """Transaction as it comes back from create(): with an id assigned by the database."""
    transaction.id = transaction_id
    return transaction

def make_transaction(**kwargs) -> Transaction:
    """Transaction with settled fields defaulted to the operation amount.

    Cross-currency cases pass settled_amount explicitly.
    """
    kwargs.setdefault("settled_amount", kwargs["amount"])
    kwargs.setdefault("settled_currency_code", kwargs["currency_code"])
    return Transaction(**kwargs)
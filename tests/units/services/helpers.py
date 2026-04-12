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
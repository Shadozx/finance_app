import pytest

from app.models import User


class TestValidateEmail:
    def test_validate_email_lowercases_and_strips(self):
        assert User(email="  Alice@Example.com  ").email == "alice@example.com"

    def test_validate_email_accepts_apostrophe(self):
        """The schema accepts it, so the model must not turn it into a 500."""
        email = "o'connor@example.com"

        assert User(email=email).email == email

    @pytest.mark.parametrize(
        "email", ["користувач@example.com", "user@münchen.de", "invalid-email"]
    )
    def test_validate_email_rejects_unsupported_address(self, email: str):
        with pytest.raises(ValueError, match="Invalid email address"):
            User(email=email)

    def test_validate_email_rejects_empty_value(self):
        with pytest.raises(ValueError, match="Email is required"):
            User(email="")

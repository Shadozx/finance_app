import re
from decimal import Decimal

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def password_validator(
        password: str
) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit")
    if not any(c.isalpha() for c in password):
        raise ValueError("Password must contain at least one letter")

    return password


def username_validator(
        username: str
) -> str:
    username = username.strip()

    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters")

    if len(username) > 50:
        raise ValueError("Username must be less than 50 characters")

    # Тільки букви, цифри, підкреслення
    if not USERNAME_PATTERN.match(username):
        raise ValueError("Username can only contain letters, numbers and underscores")

    return username

def amount_validator(amount: Decimal) -> Decimal:
    if amount < 0:
        raise ValueError("Amount cannot be negative")

    return amount

def currency_code_validator(currency_code: str) -> str:
    currency_code = currency_code.strip().upper()

    if len(currency_code) != 3:
        raise ValueError("Currency code must be 3 letters")

    return currency_code
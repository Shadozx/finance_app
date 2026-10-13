import re

# Shape of an address as stored in users.email: ASCII only, already lower-cased.
# The local part allows the RFC 5322 atext set, so it never rejects an ASCII
# address that EmailStr accepted.
STORED_EMAIL_PATTERN = re.compile(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+@[a-z0-9-]+(\.[a-z0-9-]+)+")


def normalize_email(email: str) -> str:
    """Canonical form of an address, used both to store it and to look it up."""

    return email.strip().lower()


def is_supported_email(email: str) -> bool:
    """Whether a normalized address fits what the users table stores.

    Non-ASCII local parts and internationalized domains are not supported:
    case folding and comparing them has no single answer that every mail
    provider agrees on.
    """

    return STORED_EMAIL_PATTERN.fullmatch(email) is not None

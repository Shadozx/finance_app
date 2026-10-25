import unicodedata


def normalize_password(password: str) -> str:
    """Canonical Unicode form of a password, used both to hash it and to verify it."""

    return unicodedata.normalize("NFC", password)

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.core import settings

ph = PasswordHasher()

# Verified against when the email is unknown, so that a failed login costs one Argon2 run
# either way. Computed once at import with the current hasher settings: a hardcoded hash
# would keep the parameters it was made with and drift apart from the real one.
DUMMY_PASSWORD_HASH = ph.hash("dummy-password-never-matched")


def generate_refresh_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def create_refresh_token(session_id: UUID, secret: str) -> str:
    return f"{session_id}.{secret}"


def parse_refresh_token(token: str) -> tuple[UUID, str] | None:
    session_id, separator, secret = token.partition(".")
    if not separator or not secret:
        return None

    try:
        return UUID(session_id), secret
    except ValueError:
        return None


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()

    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    # iat is written with sub-second precision (RFC 7519 allows a fractional NumericDate).
    # Whole seconds would make a token issued in the same second as a password change
    # indistinguishable from one issued before it.
    to_encode.update({"exp": expire.timestamp(), "iat": now.timestamp()})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as err:
        raise ValueError("Invalid token") from err


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False

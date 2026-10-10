import hashlib
import hmac
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


def _sign_refresh_token(session_id: UUID, secret: str) -> str:
    message = f"refresh-token:{session_id}.{secret}"
    return hmac.new(settings.SECRET_KEY.encode(), message.encode(), hashlib.sha256).hexdigest()


def create_refresh_token(session_id: UUID, secret: str) -> str:
    signature = _sign_refresh_token(session_id, secret)
    return f"{session_id}.{secret}.{signature}"


def parse_refresh_token(token: str) -> tuple[UUID, str, str] | None:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        return None

    session_id, secret, signature = parts
    try:
        return UUID(session_id), secret, signature
    except ValueError:
        return None


def verify_refresh_token_signature(session_id: UUID, secret: str, signature: str) -> bool:
    expected_signature = _sign_refresh_token(session_id, secret)
    return hmac.compare_digest(expected_signature.encode(), signature.encode())


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()

    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

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

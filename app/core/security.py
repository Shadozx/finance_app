import asyncio
import hashlib
import hmac
import secrets
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from threading import Lock
from typing import NamedTuple, TypeVar
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from jose import JWTError, jwt

from app.core import settings

T = TypeVar("T")


class PasswordHashQueueFullError(Exception):
    def __init__(self, pending_count: int):
        self.pending_count = pending_count
        super().__init__("Password hash queue is full")


class Argon2Hasher:
    """Run Argon2 in a worker pool with a limit on unfinished tasks.

    Cancelled work items remain in the executor queue until a worker skips them
    (roughly 2 KB each, depending on Python and captured objects). max_workers bounds
    concurrent Argon2 memory, not the total memory retained by cancelled queue entries.
    """

    def __init__(
        self,
        *,
        concurrency: int,
        max_queue: int,
        backend: PasswordHasher | None = None,
    ):
        if concurrency <= 0:
            raise ValueError("concurrency must be greater than zero")
        if max_queue < 0:
            raise ValueError("max_queue must not be negative")

        self._backend = backend if backend is not None else PasswordHasher()
        # Computed from this backend rather than hardcoded: a fixed hash would keep the parameters
        # it was made with, and a failed login for an unknown email would stop costing the same.
        self._dummy_password_hash = self._backend.hash("dummy-password-never-matched")
        self._executor = ThreadPoolExecutor(
            max_workers=concurrency, thread_name_prefix="password-hash"
        )
        self._capacity = concurrency + max_queue
        self._pending_count = 0
        self._lock = Lock()

    async def hash(self, password: str) -> str:
        return await self._run(partial(self._hash_password, password))

    async def verify(self, plain_password: str, hashed_password: str) -> bool:
        return await self._run(partial(self._verify_password, plain_password, hashed_password))

    async def verify_dummy(self, plain_password: str) -> bool:
        return await self.verify(plain_password, self._dummy_password_hash)

    async def _run(self, operation: Callable[[], T]) -> T:
        with self._lock:
            if self._pending_count >= self._capacity:
                raise PasswordHashQueueFullError(self._pending_count)
            self._pending_count += 1

        try:
            concurrent_future = self._executor.submit(operation)
        except BaseException:
            self._release_slot()
            raise

        # A completed future invokes this immediately, so registration must be outside the lock.
        concurrent_future.add_done_callback(lambda _: self._release_slot())
        try:
            return await asyncio.wrap_future(concurrent_future)
        except asyncio.CancelledError:
            # wrap_future forwards cancellation on a later event-loop iteration. Cancel here
            # to release a queued slot synchronously; running work keeps its slot until done.
            concurrent_future.cancel()
            raise

    def _release_slot(self) -> None:
        with self._lock:
            self._pending_count -= 1

    def _hash_password(self, password: str) -> str:
        return self._backend.hash(password)

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return self._backend.verify(hashed_password, plain_password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)


password_hasher = Argon2Hasher(
    concurrency=settings.PASSWORD_HASH_CONCURRENCY,
    max_queue=settings.PASSWORD_HASH_MAX_QUEUE,
)


class ParsedRefreshToken(NamedTuple):
    session_id: UUID
    secret: str
    signature: str


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


def parse_refresh_token(token: str) -> ParsedRefreshToken | None:
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        return None

    session_id, secret, signature = parts
    try:
        return ParsedRefreshToken(UUID(session_id), secret, signature)
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

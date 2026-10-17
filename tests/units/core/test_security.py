import asyncio
import hashlib
import hmac
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, get_ident
from unittest.mock import patch
from uuid import uuid4

import pytest
from jose import jwt
from pytest_mock import MockerFixture

from app.core.config import settings
from app.core.security import (
    Argon2Hasher,
    PasswordHashQueueFullError,
    create_access_token,
    create_refresh_token,
    fingerprint_email,
    generate_refresh_secret,
    hash_refresh_secret,
    parse_refresh_token,
    verify_refresh_token_signature,
    verify_token,
)

WORKER_TIMEOUT_SECONDS = 5
TEST_PASSWORD = "test-password"
TEST_PASSWORD_HASH = "test-password-hash"
WRONG_PASSWORD = "wrong-password"
INVALID_PASSWORD_HASH = "invalid-hash"


class BlockingPasswordBackend:
    def __init__(self, concurrency: int):
        self.concurrency = concurrency
        self.release = Event()
        self.started = Event()
        self.lock = Lock()
        self.passwords = []
        self.thread_ids = []
        self.active = 0
        self.max_active = 0

    def hash(self, password: str) -> str:
        with self.lock:
            self.passwords.append(password)
            self.thread_ids.append(get_ident())
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active == self.concurrency:
                self.started.set()
        try:
            if not self.release.wait(WORKER_TIMEOUT_SECONDS):
                raise TimeoutError("Test did not release the password worker")
            return TEST_PASSWORD_HASH
        finally:
            with self.lock:
                self.active -= 1

    def verify(self, hashed_password: str, plain_password: str) -> bool:
        return self.hash(plain_password) == hashed_password


@pytest.fixture
def make_hasher():
    hashers = []

    def factory(*, concurrency=1, max_queue=0, backend=None):
        if isinstance(backend, BlockingPasswordBackend):
            with patch.object(backend, "hash", return_value=TEST_PASSWORD_HASH):
                hasher = Argon2Hasher(concurrency=concurrency, max_queue=max_queue, backend=backend)
        else:
            hasher = Argon2Hasher(concurrency=concurrency, max_queue=max_queue, backend=backend)
        hashers.append((hasher, backend))
        return hasher

    yield factory

    for hasher, backend in hashers:
        if isinstance(backend, BlockingPasswordBackend):
            backend.release.set()
        hasher.shutdown()


async def wait_for_workers(backend: BlockingPasswordBackend) -> None:
    assert await asyncio.to_thread(backend.started.wait, WORKER_TIMEOUT_SECONDS)


class TestArgon2Hasher:
    async def test_hash_and_verify_round_trip(self, make_hasher):
        hasher = make_hasher()

        hashed_password = await hasher.hash(TEST_PASSWORD)

        assert hashed_password != TEST_PASSWORD
        assert await hasher.verify(TEST_PASSWORD, hashed_password)
        assert not await hasher.verify(WRONG_PASSWORD, hashed_password)
        assert not await hasher.verify(TEST_PASSWORD, INVALID_PASSWORD_HASH)

    async def test_verify_dummy_rejects_password(self, make_hasher):
        hasher = make_hasher()

        assert not await hasher.verify_dummy(TEST_PASSWORD)

    async def test_verify_dummy_uses_hash_generated_by_its_backend(
        self, make_hasher, mocker: MockerFixture
    ):
        backend = mocker.Mock()
        backend.hash.return_value = TEST_PASSWORD_HASH
        backend.verify.return_value = False
        hasher = make_hasher(backend=backend)

        assert not await hasher.verify_dummy(TEST_PASSWORD)

        backend.hash.assert_called_once()
        backend.verify.assert_called_once_with(TEST_PASSWORD_HASH, TEST_PASSWORD)

    @pytest.mark.parametrize("operation", ["hash", "verify", "verify_dummy"])
    async def test_operation_propagates_unexpected_error_and_releases_slot(
        self, make_hasher, mocker: MockerFixture, operation: str
    ):
        backend = mocker.Mock()
        error = RuntimeError("Backend failed")
        hasher = make_hasher(backend=backend)
        backend_method = getattr(backend, "verify" if operation == "verify_dummy" else operation)
        backend_method.side_effect = error
        args = (TEST_PASSWORD, TEST_PASSWORD_HASH) if operation == "verify" else (TEST_PASSWORD,)

        with pytest.raises(RuntimeError) as exc_info:
            await getattr(hasher, operation)(*args)

        assert exc_info.value is error
        backend_method.side_effect = None
        expected_result = TEST_PASSWORD_HASH if operation == "hash" else True
        backend_method.return_value = expected_result
        assert await getattr(hasher, operation)(*args) == expected_result

    @pytest.mark.parametrize("max_queue", [0, 2], ids=["no-queue", "queued"])
    @pytest.mark.parametrize("operation", ["hash", "verify_dummy"])
    async def test_operation_rejects_overflow_without_blocking_event_loop(
        self, make_hasher, max_queue, operation
    ):
        concurrency = 2
        capacity = concurrency + max_queue
        backend = BlockingPasswordBackend(concurrency)
        hasher = make_hasher(concurrency=concurrency, max_queue=max_queue, backend=backend)
        tasks = [asyncio.create_task(hasher.hash(TEST_PASSWORD)) for _ in range(concurrency)]
        try:
            await wait_for_workers(backend)
            tasks.extend(
                asyncio.create_task(hasher.verify(TEST_PASSWORD, TEST_PASSWORD_HASH))
                for _ in range(max_queue)
            )
            await asyncio.sleep(0)

            with pytest.raises(PasswordHashQueueFullError) as exc_info:
                await getattr(hasher, operation)(TEST_PASSWORD)

            assert exc_info.value.pending_count == capacity
            assert backend.max_active == concurrency
            assert get_ident() not in backend.thread_ids
            assert not backend.release.is_set()
        finally:
            backend.release.set()
            results = await asyncio.gather(*tasks)

        assert results == [TEST_PASSWORD_HASH] * concurrency + [True] * max_queue

    async def test_hash_cancelled_running_work_keeps_capacity_until_finished(self, make_hasher):
        concurrency = 2
        max_queue = 1
        capacity = concurrency + max_queue
        backend = BlockingPasswordBackend(concurrency)
        hasher = make_hasher(concurrency=concurrency, max_queue=max_queue, backend=backend)
        tasks = [asyncio.create_task(hasher.hash(TEST_PASSWORD)) for _ in range(concurrency)]
        try:
            await wait_for_workers(backend)
            for task in tasks:
                task.cancel()
            for task in tasks:
                with pytest.raises(asyncio.CancelledError):
                    await task

            replacement = asyncio.create_task(hasher.hash(TEST_PASSWORD))
            tasks.append(replacement)
            await asyncio.sleep(0)
            with pytest.raises(PasswordHashQueueFullError) as exc_info:
                await hasher.hash(TEST_PASSWORD)
            assert exc_info.value.pending_count == capacity
            assert len(backend.passwords) == concurrency
        finally:
            backend.release.set()
            await asyncio.gather(*tasks, return_exceptions=True)

        assert backend.max_active == concurrency
        assert await hasher.hash(TEST_PASSWORD) == TEST_PASSWORD_HASH

    async def test_hash_cancelled_queue_entry_releases_slot_before_yielding(self, make_hasher):
        concurrency = 1
        max_queue = 1
        cancelled_password = "cancelled-password"
        replacement_password = "replacement-password"
        backend = BlockingPasswordBackend(concurrency)
        hasher = make_hasher(concurrency=concurrency, max_queue=max_queue, backend=backend)
        running = asyncio.create_task(hasher.hash(TEST_PASSWORD))
        replacement = None
        queued = hasher.hash(cancelled_password)
        try:
            await wait_for_workers(backend)
            # Drive cancellation without yielding to wrap_future's scheduled callbacks.
            queued.send(None)
            with pytest.raises(asyncio.CancelledError):
                queued.throw(asyncio.CancelledError())

            assert hasher._pending_count == concurrency
            replacement = asyncio.create_task(hasher.hash(replacement_password))
            await asyncio.sleep(0)
            assert not replacement.done()
        finally:
            queued.close()
            backend.release.set()
            await running
            if replacement is not None:
                assert await replacement == TEST_PASSWORD_HASH

        assert backend.passwords == [TEST_PASSWORD, replacement_password]
        assert backend.max_active == concurrency

    async def test_hash_registers_completed_future_callback_outside_lock(
        self, make_hasher, mocker: MockerFixture
    ):
        hasher = make_hasher()

        class CompletedFuture(Future):
            def add_done_callback(self, callback):
                # Fail immediately instead of hanging the test if registration holds the lock.
                assert not hasher._lock.locked()
                super().add_done_callback(callback)

        completed = CompletedFuture()
        completed.set_result(TEST_PASSWORD_HASH)
        mocker.patch.object(hasher._executor, "submit", return_value=completed)

        assert await hasher.hash(TEST_PASSWORD) == TEST_PASSWORD_HASH
        assert hasher._pending_count == 0
        assert await hasher.hash(TEST_PASSWORD) == TEST_PASSWORD_HASH

    async def test_hash_returns_reservation_when_submit_fails(self, make_hasher, mocker):
        hasher = make_hasher()
        submit_error = RuntimeError("Submission failed")
        mocked_submit = mocker.patch.object(hasher._executor, "submit", side_effect=submit_error)

        with pytest.raises(RuntimeError) as exc_info:
            await hasher.hash(TEST_PASSWORD)

        assert exc_info.value is submit_error
        assert hasher._pending_count == 0
        mocker.stop(mocked_submit)
        assert await hasher.verify(TEST_PASSWORD, await hasher.hash(TEST_PASSWORD))

    async def test_hash_returns_reservation_after_shutdown(self, make_hasher):
        hasher = make_hasher()
        hasher.shutdown()

        for _ in range(2):
            with pytest.raises(RuntimeError, match="cannot schedule new futures after shutdown"):
                await hasher.hash(TEST_PASSWORD)
            assert hasher._pending_count == 0

    @pytest.mark.parametrize(("concurrency", "max_queue"), [(0, 0), (-1, 0), (1, -1)])
    def test_constructor_rejects_invalid_limits(self, concurrency, max_queue):
        with pytest.raises(ValueError):
            Argon2Hasher(concurrency=concurrency, max_queue=max_queue)


class TestFingerprintEmail:
    @pytest.fixture
    def email(self):
        return "user@example.com"

    def test_fingerprint_email_is_deterministic_and_uses_domain_separated_hmac(self, email: str):
        fingerprint_hex_length = 16
        message = f"log-email:{email}"
        expected_fingerprint = hmac.new(
            settings.SECRET_KEY.encode(), message.encode(), hashlib.sha256
        ).hexdigest()[:fingerprint_hex_length]

        fingerprint = fingerprint_email(email)

        assert fingerprint == fingerprint_email(email)
        assert fingerprint == expected_fingerprint
        assert len(fingerprint) == fingerprint_hex_length
        assert email not in fingerprint

    def test_fingerprint_email_ignores_email_case(self, email: str):
        mixed_case_email = email.title()

        assert fingerprint_email(mixed_case_email) == fingerprint_email(email)

    def test_fingerprint_email_differs_for_different_addresses(self, email: str):
        other_email = f"other-{email}"

        assert fingerprint_email(email) != fingerprint_email(other_email)

    def test_fingerprint_email_changes_when_secret_key_changes(
        self, email: str, mocker: MockerFixture
    ):
        original_fingerprint = fingerprint_email(email)
        rotated_key = f"{settings.SECRET_KEY}-rotated"
        mocker.patch("app.core.security.settings.SECRET_KEY", rotated_key)

        assert fingerprint_email(email) != original_fingerprint


class TestRefreshToken:
    def test_create_refresh_token_round_trips_through_parser(self):
        session_id = uuid4()
        secret = generate_refresh_secret()
        signature_hex_length = 64

        token = create_refresh_token(session_id, secret)

        parsed_token = parse_refresh_token(token)
        assert parsed_token is not None
        parsed_session_id, parsed_secret, signature = parsed_token
        assert parsed_session_id == session_id
        assert parsed_secret == secret
        assert len(signature) == signature_hex_length
        assert verify_refresh_token_signature(parsed_session_id, parsed_secret, signature)

    def test_verify_refresh_token_signature_rejects_changed_secret(self):
        session_id = uuid4()
        secret = generate_refresh_secret()
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token.signature
        replacement_character = "A" if secret[0] != "A" else "B"
        changed_secret = replacement_character + secret[1:]

        assert not verify_refresh_token_signature(session_id, changed_secret, signature)

    def test_verify_refresh_token_signature_rejects_substituted_session_id(self):
        session_id = uuid4()
        other_session_id = uuid4()
        secret = generate_refresh_secret()
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token.signature

        assert not verify_refresh_token_signature(other_session_id, secret, signature)

    @pytest.mark.parametrize("signature_kind", ["altered", "non-ascii"])
    def test_verify_refresh_token_signature_rejects_changed_signature(self, signature_kind: str):
        session_id = uuid4()
        secret = generate_refresh_secret()
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token.signature
        replacement_character = "0" if signature[0] != "0" else "1"
        if signature_kind == "non-ascii":
            replacement_character = "é"
        changed_signature = replacement_character + signature[1:]

        assert not verify_refresh_token_signature(session_id, secret, changed_signature)

    def test_verify_refresh_token_signature_rejects_signature_without_domain_prefix(self):
        session_id = uuid4()
        secret = generate_refresh_secret()
        message_without_prefix = f"{session_id}.{secret}"
        signature = hmac.new(
            settings.SECRET_KEY.encode(), message_without_prefix.encode(), hashlib.sha256
        ).hexdigest()

        assert not verify_refresh_token_signature(session_id, secret, signature)

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "no-separator",
            f"{uuid4()}.secret",
            f"{uuid4()}.secret.signature.extra",
            "not-a-uuid.secret.signature",
            f"{uuid4()}..signature",
            f"{uuid4()}.secret.",
            ".secret.signature",
        ],
        ids=[
            "empty",
            "missing-separator",
            "two-parts",
            "four-parts",
            "invalid-uuid",
            "empty-secret",
            "empty-signature",
            "empty-uuid",
        ],
    )
    def test_parse_refresh_token_rejects_malformed_tokens(self, token: str):
        assert parse_refresh_token(token) is None

    def test_hash_refresh_secret_is_deterministic_and_does_not_store_secret(self):
        secret = generate_refresh_secret()
        sha256_hex_length = 64

        hashed_secret = hash_refresh_secret(secret)

        assert hashed_secret == hash_refresh_secret(secret)
        assert hashed_secret != secret
        assert len(hashed_secret) == sha256_hex_length


class TestCreateAccessToken:
    @pytest.fixture
    def data(self):
        return {"sub": "1"}

    def test_create_access_token_keeps_the_given_payload(self, data: dict):
        payload = verify_token(create_access_token(data))

        assert payload["sub"] == data["sub"]

    def test_create_access_token_stamps_the_issue_time(self, data: dict):
        clock_tolerance = timedelta(seconds=5)

        before = datetime.now(UTC)

        payload = verify_token(create_access_token(data))

        issued_at = datetime.fromtimestamp(payload["iat"], UTC)

        assert before - clock_tolerance <= issued_at <= datetime.now(UTC) + clock_tolerance

    def test_create_access_token_expires_after_the_configured_lifetime(self, data: dict):
        payload = verify_token(create_access_token(data))

        issued_at = datetime.fromtimestamp(payload["iat"], UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)

        assert expires_at - issued_at == timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    def test_create_access_token_honours_an_explicit_lifetime(self, data: dict):
        custom_lifetime = timedelta(minutes=5)

        payload = verify_token(create_access_token(data, expires_delta=custom_lifetime))

        issued_at = datetime.fromtimestamp(payload["iat"], UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)

        assert expires_at - issued_at == custom_lifetime

    def test_create_access_token_honours_a_zero_lifetime(self, data: dict):
        zero_lifetime = timedelta(0)

        token = create_access_token(data, expires_delta=zero_lifetime)
        payload = jwt.get_unverified_claims(token)

        assert payload["exp"] == payload["iat"]


class TestVerifyToken:
    @pytest.fixture
    def data(self):
        return {"sub": "1"}

    def test_verify_token_rejects_a_token_it_did_not_sign(self, data: dict):
        foreign_secret_key = f"{settings.SECRET_KEY}-foreign"
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        foreign_token = jwt.encode(
            {**data, "exp": expires_at.timestamp()},
            foreign_secret_key,
            algorithm=settings.ALGORITHM,
        )
        assert jwt.get_unverified_claims(foreign_token)["sub"] == data["sub"]

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(foreign_token)

    def test_verify_token_rejects_a_token_without_exp(self, data: dict):
        token = jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    def test_verify_token_rejects_an_expired_token(self, data: dict):
        already_elapsed = timedelta(minutes=-5)

        expired_token = create_access_token(data, expires_delta=already_elapsed)

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(expired_token)

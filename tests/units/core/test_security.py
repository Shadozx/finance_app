import asyncio
import base64
import hashlib
import hmac
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from threading import Event, Lock, get_ident
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from argon2 import Parameters, PasswordHasher, extract_parameters, profiles
from argon2.low_level import ARGON2_VERSION
from pytest_mock import MockerFixture

from app.core.config import settings
from app.core.security import (
    ARGON2_HASH_LENGTH_BYTES,
    ARGON2_MEMORY_COST_KIB,
    ARGON2_PARALLELISM,
    ARGON2_SALT_LENGTH_BYTES,
    ARGON2_TIME_COST,
    ARGON2_TYPE,
    Argon2Hasher,
    PasswordHashQueueFullError,
    create_access_token,
    create_refresh_token,
    derive_refresh_secret,
    fingerprint_email,
    hash_refresh_secret,
    parse_refresh_token,
    verify_refresh_token_signature,
    verify_token,
)
from app.models import INITIAL_REFRESH_GENERATION
from tests.jwt_helpers import (
    FOREIGN_AUDIENCE,
    FOREIGN_ISSUER,
    ISSUER_AUDIENCE_DEFECTS,
    UNSECURED_ALGORITHM,
    ClaimsBreaker,
    assemble_test_jwt,
    encode_test_jwt,
    read_jwt_claims,
    read_jwt_header,
    replace_claim,
    sign_jwt,
    without_claim,
)

TEST_PASSWORD = "test-password"
TEST_PASSWORD_HASH = "test-password-hash"
WRONG_PASSWORD = "wrong-password"
INVALID_PASSWORD_HASH = "invalid-hash"
WORKER_TIMEOUT_SECONDS = 5

OUTDATED_PARAMETERS = profiles.CHEAPEST
# Made by argon2-cffi 25.1.0 with its defaults, before the parameters were written down
LIBRARY_DEFAULT_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$xTG0jtSXBo1s0zjGzMVedA$"
    "ML4R668SfdHu81x70RhEapqM+lwTVI3Y+5hDg8VwToI"
)

# Any secret will do for tests that sign or parse a token; the derived one is tested apart
REFRESH_SECRET = "test-refresh-secret"
OTHER_GENERATION = INITIAL_REFRESH_GENERATION + 1
REFRESH_SIGNATURE_HEX_LENGTH = 64
# Well-formed in length, but no key signs the test token this way
WRONG_REFRESH_SIGNATURE = "0" * REFRESH_SIGNATURE_HEX_LENGTH
NON_ASCII_REFRESH_SIGNATURE = "é" * REFRESH_SIGNATURE_HEX_LENGTH

MALFORMED_REFRESH_TOKENS = [
    pytest.param("", id="empty"),
    pytest.param("no-separator", id="missing_separator"),
    pytest.param(f"{uuid4()}.secret", id="two_parts"),
    pytest.param(f"{uuid4()}.secret.signature.extra", id="four_parts"),
    pytest.param("not-a-uuid.secret.signature", id="invalid_uuid"),
    pytest.param(f"{uuid4()}..signature", id="empty_secret"),
    pytest.param(f"{uuid4()}.secret.", id="empty_signature"),
    pytest.param(".secret.signature", id="empty_uuid"),
]

JWT_SEGMENT_COUNT = 3
HALF_A_SECOND_IN_MICROSECONDS = 500_000
# Keeps a fractional issue time safely in the past, whatever the clock reads
ISSUED_AT_MARGIN = timedelta(seconds=1)
FUTURE_ISSUE_OFFSET = timedelta(hours=1)
NON_STRING_SUBJECT = 1
OTHER_SIGNING_ALGORITHMS = ["HS384", "HS512", UNSECURED_ALGORITHM]

# Malformed tokens; the last two are signed correctly, so only their body can reject them
MALFORMED_TOKENS = [
    pytest.param("", id="empty"),
    pytest.param("not-a-token", id="no_dots"),
    pytest.param("one.two", id="two_segments"),
    pytest.param("a.b.c.d", id="four_segments"),
    pytest.param("!!!.!!!.!!!", id="not_base64"),
    pytest.param(assemble_test_jwt(b"not json", settings.SECRET_KEY), id="body_not_json"),
    pytest.param(assemble_test_jwt(b"[1]", settings.SECRET_KEY), id="body_not_an_object"),
]


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
def hasher_factory():
    hashers = []

    def factory(*, concurrency=1, max_queue=0, backend=None):
        if isinstance(backend, BlockingPasswordBackend):
            # The constructor hashes a dummy password at once, and a blocking backend would
            # hang there
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
    class TestInit:
        @pytest.mark.parametrize(
            ("concurrency", "max_queue"),
            [
                pytest.param(0, 0, id="zero_concurrency"),
                pytest.param(-1, 0, id="negative_concurrency"),
                pytest.param(1, -1, id="negative_max_queue"),
            ],
        )
        def test_init_invalid_limits_raises_value_error(self, concurrency, max_queue):
            with pytest.raises(ValueError):
                Argon2Hasher(concurrency=concurrency, max_queue=max_queue)

    class TestHash:
        async def test_hash_returns_hash_with_pinned_parameters(self, hasher_factory):
            hasher = hasher_factory()
            expected_parameters = Parameters(
                type=ARGON2_TYPE,
                version=ARGON2_VERSION,
                salt_len=ARGON2_SALT_LENGTH_BYTES,
                hash_len=ARGON2_HASH_LENGTH_BYTES,
                time_cost=ARGON2_TIME_COST,
                memory_cost=ARGON2_MEMORY_COST_KIB,
                parallelism=ARGON2_PARALLELISM,
            )

            hashed_password = await hasher.hash(TEST_PASSWORD)

            assert extract_parameters(hashed_password) == expected_parameters

    class TestVerify:
        async def test_verify_round_trip_returns_true_only_for_match(self, hasher_factory):
            hasher = hasher_factory()

            hashed_password = await hasher.hash(TEST_PASSWORD)

            assert hashed_password != TEST_PASSWORD
            assert await hasher.verify(TEST_PASSWORD, hashed_password)
            assert not await hasher.verify(WRONG_PASSWORD, hashed_password)
            assert not await hasher.verify(TEST_PASSWORD, INVALID_PASSWORD_HASH)

    class TestVerifyDummy:
        async def test_verify_dummy_any_password_returns_false(self, hasher_factory):
            hasher = hasher_factory()

            assert not await hasher.verify_dummy(TEST_PASSWORD)

        async def test_verify_dummy_uses_backend_hash(self, hasher_factory, mocker: MockerFixture):
            backend = mocker.Mock()
            backend.hash.return_value = TEST_PASSWORD_HASH
            backend.verify.return_value = False
            hasher = hasher_factory(backend=backend)

            assert not await hasher.verify_dummy(TEST_PASSWORD)

            backend.hash.assert_called_once()
            backend.verify.assert_called_once_with(TEST_PASSWORD_HASH, TEST_PASSWORD)

    class TestNeedsRehash:
        async def test_needs_rehash_fresh_hash_returns_false(self, hasher_factory):
            hasher = hasher_factory()

            hashed_password = await hasher.hash(TEST_PASSWORD)

            assert hasher.needs_rehash(hashed_password) is False

        async def test_needs_rehash_outdated_hash_returns_true(self, hasher_factory):
            hasher = hasher_factory()
            outdated_hashed_password = PasswordHasher.from_parameters(OUTDATED_PARAMETERS).hash(
                TEST_PASSWORD
            )

            assert hasher.needs_rehash(outdated_hashed_password) is True

        def test_needs_rehash_library_default_hash_returns_false(self, hasher_factory):
            hasher = hasher_factory()

            assert hasher.needs_rehash(LIBRARY_DEFAULT_PASSWORD_HASH) is False

    class TestRun:
        async def test_run_argon2_error_releases_hash_slot(
            self, hasher_factory, mocker: MockerFixture
        ):
            backend = mocker.Mock()
            error = RuntimeError("Backend failed")
            hasher = hasher_factory(backend=backend)
            backend.hash.side_effect = error

            with pytest.raises(RuntimeError) as exc_info:
                await hasher.hash(TEST_PASSWORD)

            assert exc_info.value is error
            # The hasher has a single slot, so the next hash runs only if the failed one
            # released it
            backend.hash.side_effect = None
            backend.hash.return_value = TEST_PASSWORD_HASH
            assert await hasher.hash(TEST_PASSWORD) == TEST_PASSWORD_HASH

        @pytest.mark.parametrize("operation", ["hash", "verify_dummy"])
        async def test_run_all_hash_slots_taken_raises_queue_full(self, hasher_factory, operation):
            concurrency = 2
            max_queue = 2
            capacity = concurrency + max_queue
            backend = BlockingPasswordBackend(concurrency)
            hasher = hasher_factory(concurrency=concurrency, max_queue=max_queue, backend=backend)
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

        async def test_run_cancelled_running_hash_keeps_slot_until_finished(self, hasher_factory):
            concurrency = 2
            max_queue = 1
            capacity = concurrency + max_queue
            backend = BlockingPasswordBackend(concurrency)
            hasher = hasher_factory(concurrency=concurrency, max_queue=max_queue, backend=backend)
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

        async def test_run_cancelled_waiting_request_releases_hash_slot(self, hasher_factory):
            concurrency = 1
            max_queue = 1
            cancelled_password = "cancelled-password"
            replacement_password = "replacement-password"
            backend = BlockingPasswordBackend(concurrency)
            hasher = hasher_factory(concurrency=concurrency, max_queue=max_queue, backend=backend)
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

        async def test_run_completed_future_releases_hash_slot_without_deadlock(
            self, hasher_factory, mocker: MockerFixture
        ):
            hasher = hasher_factory()

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

        async def test_run_pool_rejected_task_releases_hash_slot(self, hasher_factory, mocker):
            hasher = hasher_factory()
            submit_error = RuntimeError("Submission failed")
            mocked_submit = mocker.patch.object(
                hasher._executor, "submit", side_effect=submit_error
            )

            with pytest.raises(RuntimeError) as exc_info:
                await hasher.hash(TEST_PASSWORD)

            assert exc_info.value is submit_error
            assert hasher._pending_count == 0
            mocker.stop(mocked_submit)
            assert await hasher.verify(TEST_PASSWORD, await hasher.hash(TEST_PASSWORD))

        async def test_run_pool_shutdown_releases_hash_slot(self, hasher_factory):
            hasher = hasher_factory()
            hasher.shutdown()

            for _ in range(2):
                with pytest.raises(
                    RuntimeError, match="cannot schedule new futures after shutdown"
                ):
                    await hasher.hash(TEST_PASSWORD)
                assert hasher._pending_count == 0


class TestFingerprintEmail:
    @pytest.fixture
    def email(self):
        return "user@example.com"

    def test_fingerprint_email_returns_prefixed_hmac(self, email: str):
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

    def test_fingerprint_email_mixed_case_returns_same_fingerprint(self, email: str):
        mixed_case_email = email.title()

        assert fingerprint_email(mixed_case_email) == fingerprint_email(email)

    def test_fingerprint_email_other_address_returns_different_fingerprint(self, email: str):
        other_email = f"other-{email}"

        assert fingerprint_email(email) != fingerprint_email(other_email)

    def test_fingerprint_email_rotated_secret_key_returns_different_fingerprint(
        self, email: str, mocker: MockerFixture
    ):
        original_fingerprint = fingerprint_email(email)
        rotated_key = f"{settings.SECRET_KEY}-rotated"
        mocker.patch("app.core.security.settings.SECRET_KEY", rotated_key)

        assert fingerprint_email(email) != original_fingerprint

    @pytest.mark.parametrize(
        "key_name",
        [
            pytest.param("REFRESH_HMAC_KEY", id="refresh_hmac_key"),
            pytest.param("REFRESH_SECRET_KEY", id="refresh_secret_key"),
        ],
    )
    def test_fingerprint_email_rotated_other_key_returns_same_fingerprint(
        self, email: str, mocker: MockerFixture, key_name: str
    ):
        original_fingerprint = fingerprint_email(email)
        rotated_key = f"{getattr(settings, key_name)}-rotated"
        mocker.patch(f"app.core.security.settings.{key_name}", rotated_key)

        assert fingerprint_email(email) == original_fingerprint


def sign_refresh_message(key: str, session_id: UUID, secret: str) -> str:
    """Refresh signature computed straight from the format, independent of the app code."""
    message = f"refresh-token:{session_id}.{secret}"

    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def reference_refresh_secret(key: str, session_id: UUID, generation: int) -> str:
    """Derived secret computed straight from the format, independent of the app code."""
    message = f"refresh-secret:{session_id}:{generation}"
    digest = hmac.new(key.encode(), message.encode(), hashlib.sha256).digest()

    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class TestDeriveRefreshSecret:
    @pytest.fixture
    def session_id(self):
        return uuid4()

    def test_derive_refresh_secret_returns_prefixed_hmac(self, session_id: UUID):
        expected_secret = reference_refresh_secret(
            settings.REFRESH_SECRET_KEY, session_id, INITIAL_REFRESH_GENERATION
        )

        assert derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION) == expected_secret

    def test_derive_refresh_secret_same_input_returns_same_secret(self, session_id: UUID):
        assert derive_refresh_secret(session_id, OTHER_GENERATION) == derive_refresh_secret(
            session_id, OTHER_GENERATION
        )

    def test_derive_refresh_secret_other_session_returns_different_secret(self, session_id: UUID):
        other_session_id = uuid4()

        assert derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION) != (
            derive_refresh_secret(other_session_id, INITIAL_REFRESH_GENERATION)
        )

    def test_derive_refresh_secret_other_generation_returns_different_secret(
        self, session_id: UUID
    ):
        assert derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION) != (
            derive_refresh_secret(session_id, OTHER_GENERATION)
        )

    def test_derive_refresh_secret_rotated_key_returns_different_secret(
        self, mocker: MockerFixture, session_id: UUID
    ):
        original_secret = derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION)
        rotated_key = f"{settings.REFRESH_SECRET_KEY}-rotated"
        mocker.patch("app.core.security.settings.REFRESH_SECRET_KEY", rotated_key)

        assert derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION) != original_secret

    @pytest.mark.parametrize(
        "key_name",
        [
            pytest.param("SECRET_KEY", id="secret_key"),
            pytest.param("REFRESH_HMAC_KEY", id="refresh_hmac_key"),
        ],
    )
    def test_derive_refresh_secret_rotated_other_key_returns_same_secret(
        self, mocker: MockerFixture, session_id: UUID, key_name: str
    ):
        original_secret = derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION)
        rotated_key = f"{getattr(settings, key_name)}-rotated"
        mocker.patch(f"app.core.security.settings.{key_name}", rotated_key)

        assert derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION) == original_secret

    def test_derive_refresh_secret_returns_token_safe_secret(self, session_id: UUID):
        secret = derive_refresh_secret(session_id, INITIAL_REFRESH_GENERATION)
        assert "." not in secret
        assert "=" not in secret

        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))

        assert parsed_token is not None
        assert parsed_token.secret == secret


class TestCreateRefreshToken:
    def test_create_refresh_token_returns_parsable_token(self):
        session_id = uuid4()
        secret = REFRESH_SECRET

        token = create_refresh_token(session_id, secret)

        parsed_token = parse_refresh_token(token)
        assert parsed_token is not None
        parsed_session_id, parsed_secret, signature = parsed_token
        assert parsed_session_id == session_id
        assert parsed_secret == secret
        assert len(signature) == REFRESH_SIGNATURE_HEX_LENGTH
        assert verify_refresh_token_signature(parsed_session_id, parsed_secret, signature)


class TestParseRefreshToken:
    @pytest.mark.parametrize("token", MALFORMED_REFRESH_TOKENS)
    def test_parse_refresh_token_malformed_token_returns_none(self, token: str):
        assert parse_refresh_token(token) is None

    def test_parse_refresh_token_access_token_returns_none(self):
        access_token = create_access_token({"sub": "1"})

        assert parse_refresh_token(access_token) is None


class TestVerifyRefreshTokenSignature:
    def test_verify_refresh_token_signature_refresh_key_signature_returns_true(self):
        session_id = uuid4()
        secret = REFRESH_SECRET
        signature = sign_refresh_message(settings.REFRESH_HMAC_KEY, session_id, secret)

        assert verify_refresh_token_signature(session_id, secret, signature)
        assert create_refresh_token(session_id, secret) == f"{session_id}.{secret}.{signature}"

    def test_verify_refresh_token_signature_changed_secret_returns_false(self):
        session_id = uuid4()
        secret = REFRESH_SECRET
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token.signature
        replacement_character = "A" if secret[0] != "A" else "B"
        changed_secret = replacement_character + secret[1:]

        assert not verify_refresh_token_signature(session_id, changed_secret, signature)

    def test_verify_refresh_token_signature_other_session_id_returns_false(self):
        session_id = uuid4()
        other_session_id = uuid4()
        secret = REFRESH_SECRET
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token.signature

        assert not verify_refresh_token_signature(other_session_id, secret, signature)

    @pytest.mark.parametrize(
        "changed_signature",
        [
            pytest.param(WRONG_REFRESH_SIGNATURE, id="wrong"),
            pytest.param(NON_ASCII_REFRESH_SIGNATURE, id="non_ascii"),
        ],
    )
    def test_verify_refresh_token_signature_changed_signature_returns_false(
        self, changed_signature: str
    ):
        session_id = uuid4()
        secret = REFRESH_SECRET

        assert not verify_refresh_token_signature(session_id, secret, changed_signature)

    def test_verify_refresh_token_signature_signature_without_prefix_returns_false(self):
        session_id = uuid4()
        secret = REFRESH_SECRET
        message_without_prefix = f"{session_id}.{secret}"
        signature = hmac.new(
            settings.REFRESH_HMAC_KEY.encode(), message_without_prefix.encode(), hashlib.sha256
        ).hexdigest()

        assert not verify_refresh_token_signature(session_id, secret, signature)

    def test_verify_refresh_token_signature_secret_key_signature_returns_false(self):
        session_id = uuid4()
        secret = REFRESH_SECRET
        signature = sign_refresh_message(settings.SECRET_KEY, session_id, secret)

        assert not verify_refresh_token_signature(session_id, secret, signature)

    def test_verify_refresh_token_signature_rotated_refresh_key_returns_false(
        self, mocker: MockerFixture
    ):
        session_id = uuid4()
        secret = REFRESH_SECRET
        signature = sign_refresh_message(settings.REFRESH_HMAC_KEY, session_id, secret)
        rotated_key = f"{settings.REFRESH_HMAC_KEY}-rotated"
        mocker.patch("app.core.security.settings.REFRESH_HMAC_KEY", rotated_key)

        assert not verify_refresh_token_signature(session_id, secret, signature)

    @pytest.mark.parametrize(
        "key_name",
        [
            pytest.param("SECRET_KEY", id="secret_key"),
            pytest.param("REFRESH_SECRET_KEY", id="refresh_secret_key"),
        ],
    )
    def test_verify_refresh_token_signature_rotated_other_key_returns_true(
        self, mocker: MockerFixture, key_name: str
    ):
        session_id = uuid4()
        secret = REFRESH_SECRET
        signature = sign_refresh_message(settings.REFRESH_HMAC_KEY, session_id, secret)
        rotated_key = f"{getattr(settings, key_name)}-rotated"
        mocker.patch(f"app.core.security.settings.{key_name}", rotated_key)

        assert verify_refresh_token_signature(session_id, secret, signature)


class TestHashRefreshSecret:
    def test_hash_refresh_secret_returns_sha256_hex(self):
        secret = REFRESH_SECRET
        sha256_hex_length = 64

        hashed_secret = hash_refresh_secret(secret)

        assert hashed_secret == hash_refresh_secret(secret)
        assert hashed_secret != secret
        assert len(hashed_secret) == sha256_hex_length


class TestCreateAccessToken:
    @pytest.fixture
    def data(self):
        return {"sub": "1"}

    def test_create_access_token_contains_payload(self, data: dict):
        payload = verify_token(create_access_token(data))

        assert payload["sub"] == data["sub"]

    def test_create_access_token_sets_issued_at(self, data: dict):
        clock_tolerance = timedelta(seconds=5)

        before = datetime.now(UTC)

        payload = verify_token(create_access_token(data))

        issued_at = datetime.fromtimestamp(payload["iat"], UTC)

        assert before - clock_tolerance <= issued_at <= datetime.now(UTC) + clock_tolerance

    def test_create_access_token_sets_default_expiration(self, data: dict):
        payload = verify_token(create_access_token(data))

        issued_at = datetime.fromtimestamp(payload["iat"], UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)

        assert expires_at - issued_at == timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    def test_create_access_token_explicit_lifetime_sets_expiration(self, data: dict):
        custom_lifetime = timedelta(minutes=5)

        payload = verify_token(create_access_token(data, expires_delta=custom_lifetime))

        issued_at = datetime.fromtimestamp(payload["iat"], UTC)
        expires_at = datetime.fromtimestamp(payload["exp"], UTC)

        assert expires_at - issued_at == custom_lifetime

    def test_create_access_token_zero_lifetime_sets_expiration_to_issued_at(self, data: dict):
        zero_lifetime = timedelta(0)

        token = create_access_token(data, expires_delta=zero_lifetime)
        payload = read_jwt_claims(token)

        assert payload["exp"] == payload["iat"]

    def test_create_access_token_contains_only_server_claims(self, data: dict):
        token = create_access_token(data)

        assert set(read_jwt_claims(token)) == {*data, "exp", "iat", "iss", "aud"}

    def test_create_access_token_sets_issuer_and_audience(self, data: dict):
        claims = read_jwt_claims(create_access_token(data))

        assert claims["iss"] == settings.JWT_ISSUER
        assert claims["aud"] == settings.JWT_AUDIENCE

    def test_create_access_token_given_issuer_and_audience_sets_configured(self, data: dict):
        data_with_foreign_values = {**data, "iss": FOREIGN_ISSUER, "aud": FOREIGN_AUDIENCE}

        claims = read_jwt_claims(create_access_token(data_with_foreign_values))

        assert claims["iss"] == settings.JWT_ISSUER
        assert claims["aud"] == settings.JWT_AUDIENCE

    def test_create_access_token_returns_standard_signed_jwt(self, data: dict):
        token = create_access_token(data)

        assert len(token.split(".")) == JWT_SEGMENT_COUNT
        assert read_jwt_header(token)["alg"] == settings.ALGORITHM

        signing_input, _, signature = token.rpartition(".")

        assert signature == sign_jwt(
            signing_input, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )


class TestVerifyToken:
    @pytest.fixture
    def data(self):
        return {"sub": "1"}

    # Valid in every claim, so a test that breaks exactly one of them tests exactly that one
    @pytest.fixture
    def valid_claims(self, data: dict) -> dict:
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        return {
            **data,
            "exp": expires_at.timestamp(),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }

    def test_verify_token_valid_claims_returns_payload(self, valid_claims: dict):
        token = encode_test_jwt(valid_claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        assert verify_token(token) == valid_claims

    def test_verify_token_foreign_signature_raises_invalid_token(
        self, data: dict, valid_claims: dict
    ):
        foreign_secret_key = f"{settings.SECRET_KEY}-foreign"
        foreign_token = encode_test_jwt(
            valid_claims,
            foreign_secret_key,
            algorithm=settings.ALGORITHM,
        )
        assert read_jwt_claims(foreign_token)["sub"] == data["sub"]

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(foreign_token)

    def test_verify_token_missing_exp_raises_invalid_token(self, valid_claims: dict):
        token = encode_test_jwt(
            without_claim(valid_claims, "exp"), settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    def test_verify_token_fractional_time_claims_returns_payload(self, valid_claims: dict):
        issued_at = (
            datetime.now(UTC).replace(microsecond=HALF_A_SECOND_IN_MICROSECONDS) - ISSUED_AT_MARGIN
        )
        expires_at = issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        claims = {**valid_claims, "iat": issued_at.timestamp(), "exp": expires_at.timestamp()}
        assert not claims["iat"].is_integer()
        assert not claims["exp"].is_integer()

        token = encode_test_jwt(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        assert verify_token(token) == claims

    def test_verify_token_future_iat_raises_invalid_token(self, valid_claims: dict):
        issued_at = datetime.now(UTC) + FUTURE_ISSUE_OFFSET
        expires_at = issued_at + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        claims = {**valid_claims, "iat": issued_at.timestamp(), "exp": expires_at.timestamp()}

        token = encode_test_jwt(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    def test_verify_token_non_string_subject_raises_invalid_token(self, valid_claims: dict):
        token = encode_test_jwt(
            replace_claim(valid_claims, "sub", NON_STRING_SUBJECT),
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    @pytest.mark.parametrize(
        "break_claims", ISSUER_AUDIENCE_DEFECTS.values(), ids=ISSUER_AUDIENCE_DEFECTS.keys()
    )
    def test_verify_token_invalid_issuer_or_audience_raises_invalid_token(
        self, valid_claims: dict, break_claims: ClaimsBreaker
    ):
        token = encode_test_jwt(
            break_claims(valid_claims), settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    @pytest.mark.parametrize("algorithm", OTHER_SIGNING_ALGORITHMS)
    def test_verify_token_other_algorithm_raises_invalid_token(
        self, valid_claims: dict, algorithm: str
    ):
        token = encode_test_jwt(valid_claims, settings.SECRET_KEY, algorithm=algorithm)
        assert read_jwt_header(token)["alg"] == algorithm

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    @pytest.mark.parametrize("token", MALFORMED_TOKENS)
    def test_verify_token_malformed_token_raises_invalid_token(self, token: str):
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    def test_verify_token_expired_raises_invalid_token(self, data: dict):
        already_elapsed = timedelta(minutes=-5)

        expired_token = create_access_token(data, expires_delta=already_elapsed)

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(expired_token)

    def test_verify_token_refresh_token_raises_invalid_token(self):
        refresh_token = create_refresh_token(uuid4(), REFRESH_SECRET)

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(refresh_token)

    @pytest.mark.parametrize(
        "key_name",
        [
            pytest.param("REFRESH_HMAC_KEY", id="refresh_hmac_key"),
            pytest.param("REFRESH_SECRET_KEY", id="refresh_secret_key"),
        ],
    )
    def test_verify_token_rotated_other_key_returns_payload(
        self, mocker: MockerFixture, valid_claims: dict, key_name: str
    ):
        token = encode_test_jwt(valid_claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        rotated_key = f"{getattr(settings, key_name)}-rotated"
        mocker.patch(f"app.core.security.settings.{key_name}", rotated_key)

        assert verify_token(token) == valid_claims

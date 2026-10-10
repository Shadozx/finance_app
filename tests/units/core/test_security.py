import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_refresh_secret,
    hash_refresh_secret,
    parse_refresh_token,
    verify_refresh_token_signature,
    verify_token,
)


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
        signature = parsed_token[2]
        replacement_character = "A" if secret[0] != "A" else "B"
        changed_secret = replacement_character + secret[1:]

        assert not verify_refresh_token_signature(session_id, changed_secret, signature)

    def test_verify_refresh_token_signature_rejects_substituted_session_id(self):
        session_id = uuid4()
        other_session_id = uuid4()
        secret = generate_refresh_secret()
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token[2]

        assert not verify_refresh_token_signature(other_session_id, secret, signature)

    @pytest.mark.parametrize("signature_kind", ["altered", "non-ascii"])
    def test_verify_refresh_token_signature_rejects_changed_signature(self, signature_kind: str):
        session_id = uuid4()
        secret = generate_refresh_secret()
        parsed_token = parse_refresh_token(create_refresh_token(session_id, secret))
        assert parsed_token is not None
        signature = parsed_token[2]
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


class TestVerifyToken:
    @pytest.fixture
    def data(self):
        return {"sub": "1"}

    def test_verify_token_rejects_a_token_it_did_not_sign(self):
        foreign_token = "not-a-token"

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(foreign_token)

    def test_verify_token_rejects_an_expired_token(self, data: dict):
        already_elapsed = timedelta(minutes=-5)

        expired_token = create_access_token(data, expires_delta=already_elapsed)

        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(expired_token)

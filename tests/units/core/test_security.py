from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.core.security import create_access_token, verify_token


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

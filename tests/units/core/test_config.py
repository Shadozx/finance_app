import re

import pytest
from pydantic import ValidationError

from app.core.config import SESSION_IDLE_EXCEEDS_MAX_MESSAGE, Settings

TOKEN_LIFETIME_SETTING_NAMES = (
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "SESSION_IDLE_DAYS",
    "SESSION_MAX_DAYS",
    "REFRESH_TOKEN_REUSE_GRACE_SECONDS",
)


@pytest.fixture
def base_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    # Keep the tests independent of variables exported on the machine running them.
    for name in TOKEN_LIFETIME_SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    return {
        "POSTGRES_USER": "test-user",
        "POSTGRES_PASSWORD": "test-password",
        "POSTGRES_SERVER": "localhost",
        "POSTGRES_DB": "test-db",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-for-settings",
    }


def make_settings(base_settings: dict[str, str], **overrides: int) -> Settings:
    return Settings(_env_file=None, **base_settings, **overrides)  # type: ignore[arg-type, call-arg]


class TestTokenLifetimeSettings:
    def test_defaults_are_valid(self, base_settings: dict[str, str]):
        default_access_token_expire_minutes = 15
        default_session_idle_days = 30
        default_session_max_days = 90
        default_refresh_token_reuse_grace_seconds = 30

        settings = make_settings(base_settings)

        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == default_access_token_expire_minutes
        assert settings.SESSION_IDLE_DAYS == default_session_idle_days
        assert settings.SESSION_MAX_DAYS == default_session_max_days
        assert settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS == (
            default_refresh_token_reuse_grace_seconds
        )

    def test_session_idle_days_may_equal_session_max_days(self, base_settings: dict[str, str]):
        session_days = 60

        settings = make_settings(
            base_settings, SESSION_IDLE_DAYS=session_days, SESSION_MAX_DAYS=session_days
        )

        assert settings.SESSION_IDLE_DAYS == settings.SESSION_MAX_DAYS == session_days

    def test_session_idle_days_must_not_exceed_session_max_days(
        self, base_settings: dict[str, str]
    ):
        session_max_days = 60
        session_idle_days = session_max_days + 1

        with pytest.raises(
            ValidationError, match=re.escape(SESSION_IDLE_EXCEEDS_MAX_MESSAGE)
        ) as exc_info:
            make_settings(
                base_settings,
                SESSION_IDLE_DAYS=session_idle_days,
                SESSION_MAX_DAYS=session_max_days,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("SESSION_MAX_DAYS",)

    @pytest.mark.parametrize(
        "field_name",
        ["ACCESS_TOKEN_EXPIRE_MINUTES", "SESSION_IDLE_DAYS", "SESSION_MAX_DAYS"],
    )
    @pytest.mark.parametrize("value", [0, -1], ids=["zero", "negative"])
    def test_positive_setting_rejects_non_positive_value(
        self, base_settings: dict[str, str], field_name: str, value: int
    ):
        with pytest.raises(ValidationError) as exc_info:
            make_settings(base_settings, **{field_name: value})

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == (field_name,)
        assert errors[0]["type"] == "greater_than"

    def test_refresh_token_reuse_grace_seconds_accepts_zero(self, base_settings: dict[str, str]):
        no_grace_seconds = 0

        settings = make_settings(base_settings, REFRESH_TOKEN_REUSE_GRACE_SECONDS=no_grace_seconds)

        assert settings.REFRESH_TOKEN_REUSE_GRACE_SECONDS == no_grace_seconds

    def test_refresh_token_reuse_grace_seconds_rejects_negative(
        self, base_settings: dict[str, str]
    ):
        negative_grace_seconds = -1

        with pytest.raises(ValidationError) as exc_info:
            make_settings(base_settings, REFRESH_TOKEN_REUSE_GRACE_SECONDS=negative_grace_seconds)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("REFRESH_TOKEN_REUSE_GRACE_SECONDS",)
        assert errors[0]["type"] == "greater_than_equal"

import os
from enum import Enum

from pydantic import (
    AnyHttpUrl,
    Field,
    PostgresDsn,
    ValidationInfo,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

FORBIDDEN_SECRETS = {"", "changeme", "secret"}
MIN_SECRET_LENGTH = 32

# Every key setting follows the same rules: it must be strong and must differ from the keys
# listed before it. Pydantic only has the earlier fields in info.data when it validates a field,
# so Settings must declare these fields in this same order.
KEY_SETTING_NAMES = ("SECRET_KEY", "REFRESH_HMAC_KEY", "REFRESH_SECRET_KEY")

SESSION_IDLE_EXCEEDS_MAX_MESSAGE = "SESSION_IDLE_DAYS must not exceed SESSION_MAX_DAYS."


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Finance Tracker"
    VERSION: str = "1.24.0"

    ENVIRONMENT: Environment = Environment.DEV
    DEBUG: bool = False
    CORS_ORIGINS: list[AnyHttpUrl] = []

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    DATABASE_URL: PostgresDsn | None = None

    SECRET_KEY: str
    REFRESH_HMAC_KEY: str
    REFRESH_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    JWT_ISSUER: str
    JWT_AUDIENCE: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(15, gt=0)
    SESSION_IDLE_DAYS: int = Field(30, gt=0)
    SESSION_MAX_DAYS: int = Field(90, gt=0)
    REFRESH_TOKEN_REUSE_GRACE_SECONDS: int = Field(30, ge=0)
    PASSWORD_HASH_CONCURRENCY: int = Field(2, gt=0)
    PASSWORD_HASH_MAX_QUEUE: int = Field(20, ge=0)

    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('ENVIRONMENT', 'dev')}"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator(*KEY_SETTING_NAMES)
    @classmethod
    def key_must_be_strong(cls, v: str, info: ValidationInfo) -> str:
        if v.strip().lower() in FORBIDDEN_SECRETS:
            raise ValueError(f"{info.field_name} is a placeholder or empty.")
        if len(v) < MIN_SECRET_LENGTH:
            raise ValueError(f"{info.field_name} must be ≥ {MIN_SECRET_LENGTH} chars.")
        return v

    @field_validator(*KEY_SETTING_NAMES)
    @classmethod
    def key_must_differ_from_earlier_keys(cls, v: str, info: ValidationInfo) -> str:
        # An earlier key that failed its own check is missing from info.data, and that check
        # already reports it. The comparison is exact: it catches a copied key, not a similar one.
        for earlier_name in KEY_SETTING_NAMES[: KEY_SETTING_NAMES.index(info.field_name)]:
            if v == info.data.get(earlier_name):
                raise ValueError(f"{info.field_name} must differ from {earlier_name}.")
        return v

    @field_validator("JWT_ISSUER", "JWT_AUDIENCE")
    @classmethod
    def jwt_claim_must_not_be_blank(cls, v: str, info: ValidationInfo) -> str:
        # The value is compared with the token claim as is, so it is not trimmed here
        if not v.strip():
            raise ValueError(f"{info.field_name} must not be empty.")
        return v

    @field_validator("SESSION_MAX_DAYS")
    @classmethod
    def session_max_days_must_cover_idle_days(cls, v: int, info: ValidationInfo) -> int:
        # SESSION_IDLE_DAYS is missing here when it failed its own constraint,
        # which already reports the error.
        idle_days = info.data.get("SESSION_IDLE_DAYS")
        if idle_days is not None and idle_days > v:
            raise ValueError(SESSION_IDLE_EXCEEDS_MAX_MESSAGE)
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str | None, info: ValidationInfo) -> str:
        if isinstance(v, str) and v:
            return v
        d = info.data
        return (
            f"postgresql+asyncpg://{d['POSTGRES_USER']}:{d['POSTGRES_PASSWORD']}"
            f"@{d['POSTGRES_SERVER']}:{d['POSTGRES_PORT']}/{d['POSTGRES_DB']}"
        )

    @computed_field  # type: ignore[prop-decorator] # mypy can't parse @computed_field over @property
    @property
    def database_url_str(self) -> str:
        return str(self.DATABASE_URL)


settings = Settings()  # type: ignore[call-arg]

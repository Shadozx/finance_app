import os
from enum import Enum

from pydantic import field_validator, PostgresDsn, ValidationInfo, AnyHttpUrl, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_SECRETS = {"", "changeme", "secret"}
_MIN_SECRET_LENGTH = 32


class Environment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    PROJECT_NAME: str = "Finance Tracker"
    VERSION: str = "1.9.0"

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
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('ENVIRONMENT', 'dev')}"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if v.strip().lower() in _FORBIDDEN_SECRETS:
            raise ValueError("SECRET_KEY is a placeholder or empty.")
        if len(v) < _MIN_SECRET_LENGTH:
            raise ValueError(f"SECRET_KEY must be ≥ {_MIN_SECRET_LENGTH} chars.")
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

    @computed_field # type: ignore[prop-decorator] # mypy can't parse @computed_field over @property
    @property
    def database_url_str(self) -> str:
        return str(self.DATABASE_URL)


settings = Settings() # type: ignore[call-arg]

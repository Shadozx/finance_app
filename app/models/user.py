from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base, utc_now
from app.core.email_policy import is_supported_email, normalize_email

# Version of the password a new user starts with
INITIAL_PASSWORD_VERSION = 0


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(String(50), unique=True)

    email: Mapped[str] = mapped_column(String(255), unique=True)

    hashed_password: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    # Number of the current password. Changes only when the password is changed;
    # rehashing the same password with newer parameters leaves it untouched.
    password_version: Mapped[int] = mapped_column(default=INITIAL_PASSWORD_VERSION)

    @validates("email")
    def validate_email(self, key, value):
        if not value:
            raise ValueError("Email is required")

        normalized = normalize_email(value)

        if not is_supported_email(normalized):
            raise ValueError("Invalid email address")

        return normalized

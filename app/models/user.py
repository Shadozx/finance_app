import re
from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import mapped_column, Mapped, validates

from app.core import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    username: Mapped[str] = mapped_column(String(50), unique=True)

    email: Mapped[str] = mapped_column(String(255), unique=True)

    hashed_password: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    @validates("email")
    def validate_email(self, key, value):
        if not value:
            raise ValueError("Email is required")

        normalized = value.lower().strip()

        if not re.match(r"^[a-z0-9_.+-]+@[a-z0-9-]+\.[a-z0-9-.]+$", normalized):
            raise ValueError("Invalid email address")

        return normalized

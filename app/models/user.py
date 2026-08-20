import re
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base
from app.models.mixins import utc_now


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

    @validates("email")
    def validate_email(self, key, value):
        if not value:
            raise ValueError("Email is required")

        normalized = value.lower().strip()

        if not re.match(r"^[a-z0-9_.+-]+@[a-z0-9-]+\.[a-z0-9-.]+$", normalized):
            raise ValueError("Invalid email address")

        return normalized

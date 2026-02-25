from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)

    symbol: Mapped[str] = mapped_column(String(5))

    name: Mapped[str] = mapped_column(String(50))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    @validates("code")
    def validate_code(self, key, value):
        if not value:
            raise ValueError("Currency code is required")

        normalized = value.upper().strip()

        if len(normalized) != 3:
            raise ValueError("Currency code must be exactly 3 characters")

        return normalized

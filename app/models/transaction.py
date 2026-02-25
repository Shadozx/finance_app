import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Enum, String, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core import Base


class TransactionType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    description: Mapped[str | None] = mapped_column(String(1024))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    date: Mapped[date] = mapped_column(Date)

    user: Mapped["User"] = relationship()

    currency: Mapped["Currency"] = relationship()

    category: Mapped["Category | None"] = relationship()

    @validates("amount")
    def validate_amount(self, key, value):

        if value is None:
            raise ValueError("Amount is required")

        if value < 0:
            raise ValueError("Amount cannot be negative")

        return value
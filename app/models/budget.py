from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Date, CheckConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str | None] = mapped_column(String(100))

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE")
    )

    start_date: Mapped[date] = mapped_column(Date)

    end_date: Mapped[date] = mapped_column(Date)

    @validates("amount")
    def validate_amount(self, key, value):
        if value is None:
            raise ValueError("Amount is required")

        if value < 0:
            raise ValueError("Amount cannot be negative")

        return value

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_budget_amount_non_negative"),
        Index("ix_budget_user_id", "user_id"),
        UniqueConstraint(
            "user_id",
            "category_id",
            "currency_code",
            "start_date",
            "end_date",
            name="uq_budget_user_category_currency_period",
        ),
    )

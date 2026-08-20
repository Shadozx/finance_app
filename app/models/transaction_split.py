from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base
from app.models.mixins import TimestampMixin


class TransactionSplit(Base, TimestampMixin):
    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)

    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"))

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    settled_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    description: Mapped[str | None] = mapped_column(String(1024))

    @validates("amount", "settled_amount")
    def validate_amounts(self, key, value):

        if value is None:
            raise ValueError(f"{key} is required")
        if value < 0:
            raise ValueError(f"{key} cannot be negative")

        return value

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_transaction_split_amount_non_negative"),
        CheckConstraint(
            "settled_amount >= 0", name="check_transaction_split_settled_amount_non_negative"
        ),
        Index("ix_transaction_splits_transaction_id", "transaction_id"),
        Index("ix_transaction_splits_category_id", "category_id"),
    )

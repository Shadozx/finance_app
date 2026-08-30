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


class TransactionTemplateSplit(Base, TimestampMixin):
    __tablename__ = "transaction_template_splits"

    id: Mapped[int] = mapped_column(primary_key=True)

    transaction_template_id: Mapped[int] = mapped_column(
        ForeignKey("transaction_templates.id", ondelete="CASCADE")
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    description: Mapped[str | None] = mapped_column(String(1024))

    @validates("amount")
    def validate_amount(self, key, value):

        if value is None:
            raise ValueError("Amount is required")
        if value < 0:
            raise ValueError("Amount cannot be negative")

        return value

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_transaction_template_split_amount_non_negative"),
        Index("ix_transaction_template_splits_transaction_template_id", "transaction_template_id"),
        Index("ix_transaction_template_splits_category_id", "category_id"),
    )

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base
from app.models import TransactionType
from app.models.mixins import TimestampMixin


class TransactionTemplate(Base, TimestampMixin):
    __tablename__ = "transaction_templates"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    name: Mapped[str] = mapped_column(String(100))

    description: Mapped[str | None] = mapped_column(String(1024))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )

    @validates("name")
    def validate_name(self, key, value):
        if value is None:
            raise ValueError("Template name is required")

        value = value.strip()

        if len(value) < 1:
            raise ValueError("Template name must be at least 1 character")

        if len(value) > 100:
            raise ValueError("Template name must be less than 100 characters")

        return value

    @validates("amount")
    def validate_amount(self, key, value):

        if value is None:
            raise ValueError("Amount is required")

        if value < 0:
            raise ValueError("Amount cannot be negative")

        return value

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_transaction_template_name"),
        CheckConstraint("amount >= 0", name="check_template_amount_non_negative"),
        Index("ix_transaction_templates_user_id", "user_id"),
    )

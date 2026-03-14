from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Enum, String, DateTime, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base
from app.models import TransactionType


class TransactionTemplate(Base):
    __tablename__ = "transaction_templates"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    name: Mapped[str] = mapped_column(String(100))

    description: Mapped[str | None] = mapped_column(String(1024))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @validates("amount")
    def validate_amount(self, key, value):
        if value < 0:
            raise ValueError("Amount cannot be negative")
        return value

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_user_template_name'),
        CheckConstraint('amount >= 0', name='check_amount_non_negative'),
    )

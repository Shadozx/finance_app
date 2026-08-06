import enum
from datetime import date
from decimal import Decimal

import uuid
from sqlalchemy import ForeignKey, Numeric, Enum, String, Date, CheckConstraint, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core import Base


class TransactionType(str, enum.Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class TransactionKind(str, enum.Enum):
    REGULAR = "REGULAR"
    ADJUSTMENT = "ADJUSTMENT"
    TRANSFER = "TRANSFER"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))

    kind: Mapped[TransactionKind] = mapped_column(Enum(TransactionKind))

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    settled_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    settled_currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    description: Mapped[str | None] = mapped_column(String(1024))

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    date: Mapped[date] = mapped_column(Date)

    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid())

    @validates("amount", "settled_amount")
    def validate_amounts(self, key, value):

        if value is None:
            raise ValueError(f"{key} is required")
        if value < 0:
            raise ValueError(f"{key} cannot be negative")

        return value

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_transaction_amount_non_negative"),
        CheckConstraint("settled_amount >= 0", name="check_transaction_settled_amount_non_negative"),
        Index("ix_transactions_user_id_date", "user_id", "date"),
        Index("ix_transactions_account_id_date", "account_id", "date"),
        Index("ix_transactions_category_id", "category_id"),
        Index("ix_transactions_transfer_group_id", "transfer_group_id"),
    )

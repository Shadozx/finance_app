import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Enum, String, Date, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core import Base


class TransactionType(str, enum.Enum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"

class TransactionKind(str, enum.Enum):
    REGULAR = "REGULAR"
    ADJUSTMENT = "ADJUSTMENT"

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))

    kind: Mapped[TransactionKind] = mapped_column(Enum(TransactionKind))

    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))

    description: Mapped[str | None] = mapped_column(String(1024))

    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    date: Mapped[date] = mapped_column(Date)

    @validates("amount")
    def validate_amount(self, key, value):

        if value is None:
            raise ValueError("Amount is required")

        if value < 0:
            raise ValueError("Amount cannot be negative")

        return value

    __table_args__ = (
        CheckConstraint("amount >= 0", name="check_transaction_amount_non_negative"),
        Index("ix_transactions_user_id_date", "user_id", "date"),
        Index("ix_transactions_account_id_date", "account_id", "date"),
        Index("ix_transactions_category_id","category_id"),
    )

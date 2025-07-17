from typing import TYPE_CHECKING, List
import enum
from datetime import datetime

from sqlalchemy import String, Enum, ForeignKey, CheckConstraint
from sqlalchemy.orm import mapped_column, Mapped, validates, relationship

from .base import Base
from .unit import Unit
# from .transaction_category_association import TransactionCategoryAssociation

if TYPE_CHECKING:
    from .user import User
    from .category import Category

class TransactionType(enum.Enum):
    income = "income"
    expense = "expense"


class Transaction(Base):
    __tablename__ = 'transactions'

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)

    # сума грошей
    amount: Mapped[float] = mapped_column(nullable=False)

    # кількість товару чи послуги (не обов'язково)
    quantity: Mapped[float] = mapped_column(nullable=True)

    description: Mapped[str] = mapped_column(String(150), nullable=False)

    added_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    # unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=True)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    owner: Mapped["User"] = relationship(back_populates="transactions")

    # categories: Mapped[List["Category"]] = relationship(
    #     secondary="transaction_category_association",
    #     back_populates="transactions",
    # )

    categories: Mapped[List["Category"]] = relationship(
        secondary="transaction_category_association",
        viewonly=True
    )

    categories_associations: Mapped[List["TransactionCategoryAssociation"]] = relationship(
        back_populates="transaction",
    )

    __table_args__ = (
        CheckConstraint('amount >= 0', name='amount_non_negative'),
        CheckConstraint('quantity >= 0', name='quantity_non_negative'),
    )

    @validates('amount')
    def validate_amount(self, key, value):
        if value < 0:
            raise ValueError("Amount cannot be negative")
        return value

    @validates('quantity')
    def validate_quantity(self, key, value):
        if value < 0:
            raise ValueError("Quantity cannot be negative")
        return value

    def __repr__(self):
        return f"Transaction(id={self.id}, description={self.description} type={self.type}, amount={self.amount}, quantity={self.quantity}, owner={self.owner.username})"



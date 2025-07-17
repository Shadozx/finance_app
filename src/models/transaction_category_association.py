from typing import TYPE_CHECKING

from datetime import datetime

from sqlalchemy import Integer, ForeignKey, DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship

from .base import Base

if TYPE_CHECKING:
    from .transaction import Transaction
    from .category import Category


class TransactionCategoryAssociation(Base):
    __tablename__ = 'transaction_category_association'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    transaction_id: Mapped[int] = mapped_column(ForeignKey('transactions.id'))

    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'))

    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    transaction: Mapped["Transaction"] = relationship(
        back_populates="categories_associations"
    )

    category: Mapped["Category"] = relationship(
        back_populates="transactions_associations"
    )

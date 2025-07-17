from typing import TYPE_CHECKING, List
from sqlalchemy import String, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# from .transaction_category_association import TransactionCategoryAssociation
if TYPE_CHECKING:
    from .transaction import Transaction


class Category(Base):
    __tablename__ = 'categories'

    name: Mapped[str] = mapped_column(String(75), nullable=False)

    # user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)

    # __table_args__ = (
    #     UniqueConstraint('user_id', 'name', name='user_id_category_name'),
    # )

    # transactions: Mapped[List["Transaction"]] = relationship(
    #     secondary="transaction_category_association",
    #     back_populates="categories",
    # )

    transactions: Mapped[List["Transaction"]] = relationship(
        secondary="transaction_category_association",
        viewonly=True
    )

    transactions_associations: Mapped[List["TransactionCategoryAssociation"]] = relationship(
        back_populates="category"
    )

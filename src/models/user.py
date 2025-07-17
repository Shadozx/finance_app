from typing import TYPE_CHECKING
import re

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from .base import Base

if TYPE_CHECKING:
    from .transaction import Transaction

class User(Base):
    __tablename__ = 'users'

    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    password: Mapped[str] = mapped_column(String(255), nullable=False)

    transactions: Mapped[list['Transaction']] = relationship(back_populates="owner")

    @validates('email')
    def validate_email(self, key, address):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", address):
            raise ValueError(f"Invalid email address: {address}")
        return address
